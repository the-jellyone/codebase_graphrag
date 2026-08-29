"""
Indexing Stage Progress Tracker.

Tracks the 5-stage indexing pipeline per repo_id in memory (with SQLite persistence).
Stages: cloning → parsing → building_graph → embedding → ready

Thread-safe via threading.Lock. Exposes callbacks for the ingestion pipeline to
call as each stage completes or progresses.

Status summary:
  pending    — not started yet
  in_progress — currently running
  done       — completed successfully
  error      — failed
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional

# Stage definitions (ordered)
STAGES = ["cloning", "parsing", "building_graph", "embedding", "ready"]

# Global in-memory state: repo_id -> stages dict
_state: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_stages() -> list[dict[str, Any]]:
    return [
        {"name": stage, "status": "pending", "percent": 0, "detail": ""}
        for stage in STAGES
    ]


def init_repo(repo_id: str) -> None:
    """Initialize tracking state for a new repo. Resets any prior state."""
    with _lock:
        _state[repo_id] = {
            "status": "idle",
            "stages": _default_stages(),
            "started_at": None,
            "finished_at": None,
            "error": None,
        }


def start_indexing(repo_id: str) -> None:
    """Mark indexing as started for a repo."""
    with _lock:
        if repo_id not in _state:
            _state[repo_id] = {
                "status": "idle",
                "stages": _default_stages(),
                "started_at": None,
                "finished_at": None,
                "error": None,
            }
        _state[repo_id]["status"] = "indexing"
        _state[repo_id]["started_at"] = _utcnow()
        _state[repo_id]["error"] = None


def update_stage(
    repo_id: str,
    stage_name: str,
    status: str,
    percent: int = 0,
    detail: str = "",
) -> None:
    """Update the status/percent/detail of a specific stage."""
    if stage_name not in STAGES:
        return
    with _lock:
        if repo_id not in _state:
            return
        for stage in _state[repo_id]["stages"]:
            if stage["name"] == stage_name:
                stage["status"] = status
                stage["percent"] = percent
                stage["detail"] = detail
                break


def complete_stage(repo_id: str, stage_name: str, detail: str = "") -> None:
    """Mark a stage as 100% done."""
    update_stage(repo_id, stage_name, "done", 100, detail)


def start_stage(repo_id: str, stage_name: str, detail: str = "") -> None:
    """Mark a stage as in_progress at 0%."""
    update_stage(repo_id, stage_name, "in_progress", 0, detail)


def set_stage_percent(repo_id: str, stage_name: str, percent: int) -> None:
    """Update only the percentage of an in-progress stage."""
    with _lock:
        if repo_id not in _state:
            return
        for stage in _state[repo_id]["stages"]:
            if stage["name"] == stage_name:
                stage["percent"] = max(0, min(100, percent))
                break


def finish_indexing(repo_id: str) -> None:
    """Mark all stages done and set overall status to 'ready'."""
    with _lock:
        if repo_id not in _state:
            return
        for stage in _state[repo_id]["stages"]:
            if stage["status"] != "done":
                stage["status"] = "done"
                stage["percent"] = 100
        _state[repo_id]["status"] = "ready"
        _state[repo_id]["finished_at"] = _utcnow()


def fail_indexing(repo_id: str, error: str) -> None:
    """Mark indexing as failed."""
    with _lock:
        if repo_id not in _state:
            return
        _state[repo_id]["status"] = "error"
        _state[repo_id]["error"] = error
        _state[repo_id]["finished_at"] = _utcnow()
        # Mark in-progress stage as error
        for stage in _state[repo_id]["stages"]:
            if stage["status"] == "in_progress":
                stage["status"] = "error"


def get_status(repo_id: str) -> Optional[dict[str, Any]]:
    """Return the current indexing status for a repo, or None if not tracked."""
    with _lock:
        if repo_id not in _state:
            return None
        # Deep copy to avoid race conditions on read
        import copy
        return copy.deepcopy(_state[repo_id])


def get_dot_color(repo_id: str) -> str:
    """Return 'green' | 'amber' | 'grey' for the sidebar status dot."""
    with _lock:
        if repo_id not in _state:
            return "grey"
        status = _state[repo_id]["status"]
    if status == "ready":
        return "green"
    if status == "indexing":
        return "amber"
    return "grey"
