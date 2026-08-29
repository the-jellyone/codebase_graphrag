"""
SQLite persistence layer for CodeGraph.

Three tables:
  repos    — registered repos with status, source, and timestamps
  chats    — chat sessions scoped to a repo_id with auto-title
  messages — message history with agent trace, is_partial, highlighted_nodes

All datetimes stored as ISO-8601 UTC strings.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path("data/codegraph.db")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with row_factory."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS repos (
            repo_id     TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            source      TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'idle',
            last_synced TEXT,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chats (
            chat_id    TEXT PRIMARY KEY,
            repo_id    TEXT NOT NULL,
            title      TEXT NOT NULL DEFAULT 'New Chat',
            created_at TEXT NOT NULL,
            FOREIGN KEY (repo_id) REFERENCES repos(repo_id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            msg_id           TEXT PRIMARY KEY,
            chat_id          TEXT NOT NULL,
            role             TEXT NOT NULL,
            content          TEXT NOT NULL,
            mode             TEXT NOT NULL DEFAULT 'graph_rag',
            trace            TEXT,
            is_partial       INTEGER NOT NULL DEFAULT 0,
            highlighted_nodes TEXT,
            created_at       TEXT NOT NULL,
            FOREIGN KEY (chat_id) REFERENCES chats(chat_id)
        );
        """)


# ---------------------------------------------------------------------------
# Repo CRUD
# ---------------------------------------------------------------------------

def create_repo(source: str, name: str) -> str:
    """Register a new repo. Returns the generated repo_id."""
    repo_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO repos (repo_id, name, source, status, created_at) VALUES (?, ?, ?, 'idle', ?)",
            (repo_id, name, source, _utcnow()),
        )
    return repo_id


def get_repo(repo_id: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM repos WHERE repo_id = ?", (repo_id,)).fetchone()
        return dict(row) if row else None


def list_repos() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM repos ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def update_repo_status(repo_id: str, status: str, last_synced: Optional[str] = None) -> None:
    """Update repo status: 'idle' | 'indexing' | 'ready' | 'error'."""
    with get_connection() as conn:
        if last_synced:
            conn.execute(
                "UPDATE repos SET status = ?, last_synced = ? WHERE repo_id = ?",
                (status, last_synced, repo_id),
            )
        else:
            conn.execute(
                "UPDATE repos SET status = ? WHERE repo_id = ?",
                (status, repo_id),
            )


def find_repo_by_source(source: str) -> Optional[dict[str, Any]]:
    """Find an existing repo by its source path or URL."""
    norm = source.strip().rstrip("/")
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM repos WHERE source = ? OR source = ? OR name = ?",
            (source, norm, norm.split("/")[-1]),
        ).fetchone()
        return dict(row) if row else None


def delete_repo(repo_id: str) -> bool:
    """Delete a repo and all its associated chats and messages."""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM messages WHERE chat_id IN (SELECT chat_id FROM chats WHERE repo_id = ?)",
            (repo_id,),
        )
        conn.execute("DELETE FROM chats WHERE repo_id = ?", (repo_id,))
        conn.execute("DELETE FROM repos WHERE repo_id = ?", (repo_id,))
    return True


# ---------------------------------------------------------------------------
# Chat CRUD
# ---------------------------------------------------------------------------

def create_chat(repo_id: str, title: str = "New Chat") -> str:
    """Create a new chat session. Returns chat_id."""
    chat_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chats (chat_id, repo_id, title, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, repo_id, title, _utcnow()),
        )
    return chat_id


def list_chats(repo_id: Optional[str] = None) -> list[dict[str, Any]]:
    with get_connection() as conn:
        if repo_id:
            rows = conn.execute(
                """SELECT c.*, r.name AS repo_name FROM chats c
                   LEFT JOIN repos r ON c.repo_id = r.repo_id
                   WHERE c.repo_id = ? ORDER BY c.created_at DESC""",
                (repo_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT c.*, r.name AS repo_name FROM chats c
                   LEFT JOIN repos r ON c.repo_id = r.repo_id
                   ORDER BY c.created_at DESC"""
            ).fetchall()
        return [dict(r) for r in rows]


def update_chat_title(chat_id: str, title: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE chats SET title = ? WHERE chat_id = ?", (title, chat_id))


def update_chat_repo(chat_id: str, repo_id: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE chats SET repo_id = ? WHERE chat_id = ?", (repo_id, chat_id))


def delete_chat(chat_id: str) -> bool:
    with get_connection() as conn:
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
    return True


def get_chat(chat_id: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT c.*, r.name AS repo_name FROM chats c
               LEFT JOIN repos r ON c.repo_id = r.repo_id
               WHERE c.chat_id = ?""",
            (chat_id,),
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Message CRUD
# ---------------------------------------------------------------------------

def save_message(
    chat_id: str,
    role: str,
    content: str,
    mode: str = "graph_rag",
    trace: Optional[list] = None,
    is_partial: bool = False,
    highlighted_nodes: Optional[list] = None,
) -> str:
    """Persist a message. Returns msg_id."""
    msg_id = str(uuid.uuid4())
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO messages
               (msg_id, chat_id, role, content, mode, trace, is_partial, highlighted_nodes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg_id,
                chat_id,
                role,
                content,
                mode,
                json.dumps(trace) if trace else None,
                1 if is_partial else 0,
                json.dumps(highlighted_nodes) if highlighted_nodes else None,
                _utcnow(),
            ),
        )
    return msg_id


def list_messages(chat_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC",
            (chat_id,),
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["trace"] = json.loads(d["trace"]) if d.get("trace") else []
        d["highlighted_nodes"] = json.loads(d["highlighted_nodes"]) if d.get("highlighted_nodes") else []
        d["is_partial"] = bool(d["is_partial"])
        result.append(d)
    return result


def count_messages(chat_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT count(*) AS n FROM messages WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return row["n"] if row else 0


# ---------------------------------------------------------------------------
# Auto-title generation
# ---------------------------------------------------------------------------

def generate_title(text: str) -> str:
    """Generate a short 3-6 word title from the first user message."""
    # Clean up the text
    cleaned = text.strip().replace("\n", " ")
    words = cleaned.split()
    # Take first 5 words, title-case, strip trailing punctuation
    title_words = words[:5]
    title = " ".join(title_words)
    # Trim trailing punctuation
    while title and title[-1] in "?.!,;:":
        title = title[:-1]
    return title or "New Chat"
