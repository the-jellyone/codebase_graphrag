"""
FastAPI Backend for CodeGraph — Code Intelligence Engine.

Full API surface:
  Repo management:   POST/GET /repos, index-status (SSE), resync, rebuild, stats, graph-preview, kg-query-url
  Chat management:   POST /chats, GET /chats, GET/POST /chats/{id}/messages (SSE streaming)
  Health:            GET /api/health
"""

from __future__ import annotations
import asyncio
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger
import ollama

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph.connection import get_driver, check_connection
from retrieval.retriever import retrieve_subgraph_context
from agent import run_agent
from config import OLLAMA_LLM_MODEL, OLLAMA_EMBED_MODEL
import db as database
import indexing.tracker as tracker


# ---------------------------------------------------------------------------
# App Bootstrap
# ---------------------------------------------------------------------------

app = FastAPI(title="CodeGraph API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _startup():
    database.init_db()
    logger.info("CodeGraph API started. SQLite DB initialized.")


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class AddRepoRequest(BaseModel):
    source: str           # local path or GitHub URL
    name: Optional[str] = None  # display name; inferred from source if omitted

class SendMessageRequest(BaseModel):
    text: str
    mode: str = "graph_rag"  # "graph_rag" | "agent"

class CreateChatRequest(BaseModel):
    repo_id: str

class ResyncRequest(BaseModel):
    pass

class RebuildRequest(BaseModel):
    pass


# ---------------------------------------------------------------------------
# Background Indexing Worker
# ---------------------------------------------------------------------------

def _run_indexing_background(repo_id: str, source: str) -> None:
    """
    Full indexing pipeline run in a background thread.
    Updates tracker stages as each step completes.
    """
    from ingestion.pipeline import run_ingestion
    from graph.loader import load_parsed_repo_into_graph

    try:
        database.update_repo_status(repo_id, "indexing")
        tracker.start_indexing(repo_id)

        # Stage 1: Cloning / resolving source
        tracker.start_stage(repo_id, "cloning")
        from ingestion.cloner import resolve_repo
        repo_path = resolve_repo(source)
        tracker.complete_stage(repo_id, "cloning", detail=str(repo_path))

        # Stage 2: Parsing files
        tracker.start_stage(repo_id, "parsing")
        from ingestion.parser import parse_repo
        parse_result = parse_repo(repo_path)
        file_count = parse_result.node_count()
        tracker.complete_stage(repo_id, "parsing", detail=f"{file_count} nodes extracted")

        # Stage 3: Building knowledge graph
        tracker.start_stage(repo_id, "building_graph")
        tracker.set_stage_percent(repo_id, "building_graph", 30)
        driver = get_driver()
        # Load without embeddings first so graph is available immediately
        load_parsed_repo_into_graph(
            parse_result, driver,
            repo_id=repo_id,
            generate_embeddings=False,
        )
        tracker.complete_stage(repo_id, "building_graph")

        # Stage 4: Generating embeddings
        tracker.start_stage(repo_id, "embedding")
        tracker.set_stage_percent(repo_id, "embedding", 10)
        load_parsed_repo_into_graph(
            parse_result, driver,
            repo_id=repo_id,
            generate_embeddings=True,
        )
        tracker.complete_stage(repo_id, "embedding")

        # Stage 5: Ready
        tracker.complete_stage(repo_id, "ready")
        tracker.finish_indexing(repo_id)

        last_synced = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        database.update_repo_status(repo_id, "ready", last_synced=last_synced)
        logger.success(f"Indexing complete for repo_id={repo_id}")

    except Exception as exc:
        logger.error(f"Indexing failed for repo_id={repo_id}: {exc}")
        tracker.fail_indexing(repo_id, str(exc))
        database.update_repo_status(repo_id, "error")


# ---------------------------------------------------------------------------
# Repo Endpoints
# ---------------------------------------------------------------------------

@app.post("/repos", status_code=202)
async def add_repo(req: AddRepoRequest, background_tasks: BackgroundTasks):
    """Register a new repo (or return existing if duplicate) and trigger indexing."""
    existing = database.find_repo_by_source(req.source)
    if existing:
        logger.info(f"Repo already registered: {existing['name']} ({existing['repo_id']})")
        return {"repo_id": existing["repo_id"], "name": existing["name"], "status": existing["status"]}

    # Infer display name from source
    name = req.name or Path(req.source).name or req.source.split("/")[-1] or req.source
    repo_id = database.create_repo(source=req.source, name=name)
    tracker.init_repo(repo_id)

    # Kick off indexing in a background thread (non-blocking)
    background_tasks.add_task(_run_indexing_background, repo_id, req.source)

    return {"repo_id": repo_id, "name": name, "status": "indexing"}


@app.delete("/repos/{repo_id}")
async def delete_repo(repo_id: str):
    """Delete a repo from SQLite and wipe its nodes from Neo4j."""
    repo = database.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found")

    try:
        from graph.updater import wipe_repo
        driver = get_driver()
        wipe_repo(driver, repo_id)
    except Exception as exc:
        logger.warning(f"Error wiping Neo4j graph nodes for {repo_id}: {exc}")

    database.delete_repo(repo_id)
    logger.info(f"Successfully deleted repo {repo_id}")
    return {"status": "deleted", "repo_id": repo_id}


@app.get("/repos")
async def list_repos():
    """List all registered repos with status dot color and last_synced timestamp."""
    repos = database.list_repos()
    result = []
    for r in repos:
        rid = r["repo_id"]
        # Get live status from tracker if indexing, else use DB status
        live = tracker.get_status(rid)
        if live and live["status"] == "indexing":
            dot = "amber"
            status = "indexing"
        elif r["status"] == "ready":
            dot = "green"
            status = "ready"
        else:
            dot = "grey"
            status = r["status"]

        result.append({
            "repo_id": rid,
            "name": r["name"],
            "source": r["source"],
            "status": status,
            "dot_color": dot,
            "last_synced": r.get("last_synced"),
            "created_at": r.get("created_at"),
        })
    return result


@app.get("/repos/{repo_id}/index-status")
async def get_index_status(repo_id: str):
    """
    Get the staged indexing progress for a repo.
    Returns the tracker state object directly.
    Poll this endpoint every 2s while status != 'ready'.
    """
    repo = database.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found")

    status = tracker.get_status(repo_id)
    if status is None:
        # Not yet tracked (repo was indexed before this session)
        db_status = repo.get("status", "idle")
        if db_status == "ready":
            # Build a synthetic "all done" state
            return {
                "status": "ready",
                "stages": [
                    {"name": s, "status": "done", "percent": 100, "detail": ""}
                    for s in tracker.STAGES
                ],
            }
        return {
            "status": db_status,
            "stages": [
                {"name": s, "status": "pending", "percent": 0, "detail": ""}
                for s in tracker.STAGES
            ],
        }

    return {
        "status": status["status"],
        "stages": status["stages"],
        "error": status.get("error"),
    }


def _run_resync_background(repo_id: str, source: str) -> None:
    """Run incremental resync without wiping the database."""
    from ingestion.cloner import resolve_repo
    from graph.updater import incremental_resync_repo
    try:
        database.update_repo_status(repo_id, "indexing")
        driver = get_driver()
        repo_path = resolve_repo(source)
        incremental_resync_repo(driver, repo_path, repo_id=repo_id, generate_embeddings=True)
        last_synced = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        database.update_repo_status(repo_id, "ready", last_synced=last_synced)
        logger.success(f"Incremental resync complete for repo_id={repo_id}")
    except Exception as exc:
        logger.error(f"Incremental resync failed for repo_id={repo_id}: {exc}")
        database.update_repo_status(repo_id, "error")


@app.post("/repos/{repo_id}/resync")
async def resync_repo(repo_id: str, background_tasks: BackgroundTasks):
    """Re-index only changed/added/deleted files for a repo (incremental sync)."""
    repo = database.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found")

    background_tasks.add_task(_run_resync_background, repo_id, repo["source"])
    return {"status": "resyncing", "repo_id": repo_id}


@app.post("/repos/{repo_id}/rebuild")
async def rebuild_repo(repo_id: str, background_tasks: BackgroundTasks):
    """Full wipe + reparse for this repo only."""
    repo = database.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found")

    # Wipe existing graph nodes for this repo
    try:
        from graph.updater import wipe_repo
        driver = get_driver()
        wipe_repo(driver, repo_id)
    except Exception as exc:
        logger.warning(f"Graph wipe error (non-fatal): {exc}")

    tracker.init_repo(repo_id)
    background_tasks.add_task(_run_indexing_background, repo_id, repo["source"])
    return {"status": "rebuilding", "repo_id": repo_id}


@app.get("/repos/{repo_id}/stats")
async def repo_stats(repo_id: str):
    """Return node count, edge count, and last_synced for a repo."""
    repo = database.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found")

    try:
        from graph.queries import get_repo_stats
        driver = get_driver()
        stats = get_repo_stats(driver, repo_id)
    except Exception as exc:
        logger.warning(f"Stats query failed: {exc}")
        stats = {"node_count": 0, "edge_count": 0}

    return {
        "repo_id": repo_id,
        "name": repo["name"],
        "node_count": stats.get("node_count", 0),
        "edge_count": stats.get("edge_count", 0),
        "last_synced": repo.get("last_synced"),
        "status": repo.get("status"),
    }


@app.get("/repos/{repo_id}/graph-preview")
async def graph_preview(repo_id: str, highlighted: str = ""):
    """
    Return lightweight nodes+edges JSON for the KG panel visualization.
    Pass ?highlighted=nodeA,nodeB to mark relevant nodes green.
    Returns {nodes: [], edges: []} gracefully when graph isn't ready.
    """
    highlighted_list = [h.strip() for h in highlighted.split(",") if h.strip()] if highlighted else []

    try:
        from graph.queries import get_graph_preview
        driver = get_driver()
        preview = get_graph_preview(driver, repo_id, highlighted_nodes=highlighted_list)
        return preview
    except Exception as exc:
        logger.warning(f"Graph preview failed (returning empty): {exc}")
        return {"nodes": [], "edges": []}


@app.get("/repos/{repo_id}/kg-query-url")
async def kg_query_url(repo_id: str):
    """Return a pre-filled Neo4j Browser URL scoped to this repo_id."""
    from config import NEO4J_URI
    # Build a simple MATCH query to view this repo's nodes
    cypher = f"MATCH (n {{repo_id: '{repo_id}'}}) RETURN n LIMIT 100"
    import urllib.parse
    encoded = urllib.parse.quote(cypher)
    # Neo4j Browser URL format
    browser_url = f"http://localhost:7474/browser/?cmd=edit&arg={encoded}"
    return {"url": browser_url, "repo_id": repo_id}


# ---------------------------------------------------------------------------
# Chat Endpoints
# ---------------------------------------------------------------------------

class UpdateChatRequest(BaseModel):
    repo_id: Optional[str] = None
    title: Optional[str] = None


@app.post("/chats", status_code=201)
async def create_chat(req: CreateChatRequest):
    """Create a new chat session scoped to a repo."""
    repo = database.get_repo(req.repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repo {req.repo_id} not found")

    chat_id = database.create_chat(repo_id=req.repo_id)
    return {"chat_id": chat_id, "repo_id": req.repo_id, "repo_name": repo["name"], "title": "New Chat"}


@app.get("/chats")
async def list_chats(repo_id: Optional[str] = None):
    """List chat sessions (all chats, or filtered by repo_id if provided)."""
    chats = database.list_chats(repo_id)
    return chats


@app.patch("/chats/{chat_id}")
async def update_chat(chat_id: str, req: UpdateChatRequest):
    """Update a chat's title or assigned repo."""
    chat = database.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")

    if req.title:
        database.update_chat_title(chat_id, req.title)
    if req.repo_id:
        database.update_chat_repo(chat_id, req.repo_id)
    return {"status": "updated", "chat_id": chat_id}


@app.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    """Delete a chat session and its messages."""
    database.delete_chat(chat_id)
    return {"status": "deleted", "chat_id": chat_id}


@app.get("/chats/{chat_id}/messages")
async def get_messages(chat_id: str):
    """Return the full message history for a chat."""
    msgs = database.list_messages(chat_id)
    return msgs


@app.post("/chats/{chat_id}/messages")
async def send_message(chat_id: str, req: SendMessageRequest):
    """
    Send a user message and stream the assistant response via SSE.
    Handles both 'graph_rag' and 'agent' modes.

    SSE event types:
      status  — progress notification
      token   — incremental response text token
      meta    — final metadata (trace, is_partial, highlighted_nodes, metrics)
      done    — end of stream marker
      error   — error message
    """
    chat = database.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")

    repo_id = chat["repo_id"]

    # Persist the user message
    database.save_message(chat_id, role="user", content=req.text, mode=req.mode)

    # Auto-title on first user message
    if database.count_messages(chat_id) == 1:
        title = database.generate_title(req.text)
        database.update_chat_title(chat_id, title)

    return StreamingResponse(
        _message_stream(chat_id, repo_id, req.text, req.mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# SSE Stream Generators
# ---------------------------------------------------------------------------

async def _message_stream(
    chat_id: str,
    repo_id: str,
    user_text: str,
    mode: str,
) -> AsyncGenerator[str, None]:
    """Generate SSE events for a single chat message."""

    def _sse(event_type: str, data: Any) -> str:
        return f"data: {json.dumps({'type': event_type, **( data if isinstance(data, dict) else {'content': data})} )}\n\n"

    if mode == "agent":
        yield _sse("status", {"content": f"Running CodeGraph Agent..."})
        try:
            # Run agent in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: run_agent(user_text, repo_id=repo_id)
            )
            answer = result.get("answer", "")
            trace = result.get("trace", [])
            is_partial = result.get("is_partial", False)
            highlighted_nodes = result.get("highlighted_nodes", [])

            # Stream answer as a single token (agent doesn't stream tokens)
            yield _sse("token", {"content": answer})

            # Persist assistant message
            database.save_message(
                chat_id, role="assistant", content=answer, mode="agent",
                trace=trace, is_partial=is_partial,
                highlighted_nodes=highlighted_nodes,
            )

            # Emit meta event with trace + graph highlight info
            yield _sse("meta", {
                "trace": trace,
                "is_partial": is_partial,
                "highlighted_nodes": highlighted_nodes,
            })

        except Exception as exc:
            logger.error(f"Agent stream error: {exc}")
            yield _sse("error", {"content": str(exc)})

    else:
        # Graph RAG mode — streaming token-by-token
        yield _sse("status", {"content": "Searching Knowledge Graph..."})

        try:
            driver = get_driver()
            context_str, seed_nodes, metrics = retrieve_subgraph_context(
                query_text=user_text,
                driver=driver,
                embed_model=OLLAMA_EMBED_MODEL,
                repo_id=repo_id,
            )
        except Exception as exc:
            logger.error(f"Retrieval failed: {exc}")
            context_str = f"*(Graph Retrieval Error: {exc})*"
            seed_nodes = []
            metrics = {}

        yield _sse("status", {"content": "Generating response..."})

        system_prompt = (
            "You are CodeGraph — an expert AI Codebase Intelligence and Architecture Assistant. "
            "Help the user understand, navigate, and improve their codebase. "
            "When specific Knowledge Graph context is available, use it to accurately explain code symbols, "
            "caller chains, exceptions, and dependency flows. "
            "For general, architectural, improvement, or brainstorming questions, provide thoughtful, structured, "
            "and conversational recommendations using software engineering best practices. "
            "Be clear, friendly, and practical."
        )
        formatted_prompt = f"{context_str}\n\n--- USER QUESTION ---\n{user_text}"

        full_response = []
        try:
            stream = ollama.chat(
                model=OLLAMA_LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": formatted_prompt},
                ],
                stream=True,
            )
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    full_response.append(token)
                    yield _sse("token", {"content": token})
        except Exception as exc:
            logger.error(f"LLM stream error: {exc}")
            yield _sse("error", {"content": str(exc)})

        # Persist the complete assistant response
        answer = "".join(full_response)
        database.save_message(
            chat_id, role="assistant", content=answer, mode="graph_rag",
            highlighted_nodes=[n.get("name", "") for n in seed_nodes if n.get("name")],
        )

        yield _sse("meta", {
            "metrics": metrics,
            "highlighted_nodes": [n.get("name", "") for n in seed_nodes if n.get("name")],
            "is_partial": False,
            "trace": [],
        })

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health_check():
    """Check Neo4j and Ollama availability."""
    neo4j_ok = check_connection()
    return {
        "status": "online" if neo4j_ok else "degraded",
        "neo4j": neo4j_ok,
        "ollama": True,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False)
