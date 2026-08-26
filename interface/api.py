"""
FastAPI Backend for Codebase Graph RAG.

Features:
- Conversational Query Rewriting (Contextual memory across multi-turn chats)
- SSE Token Streaming for real-time LLM response
- Local Chat Session Persistence (data/chats/<session_id>.json)
- Repository Indexing & Health Checks
"""

from __future__ import annotations
import sys
from pathlib import Path

# Ensure project root is in sys.path when executed directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
import os
import time
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from loguru import logger
import ollama

from graph.connection import get_driver, check_connection

from retrieval.retriever import retrieve_subgraph_context


# ---------------------------------------------------------------------------
# App Initialization & Storage Setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Codebase Graph RAG API", version="1.0.0")

# Enable CORS for React Frontend (typically running on 3000 or 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHATS_DIR = Path("data/chats")
CHATS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Request & Response Models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str   # "user" | "assistant" | "system"
    content: str


class ChatStreamRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: f"session_{int(time.time())}")
    messages: list[ChatMessage]
    model_name: str = "qwen3:4b"
    embed_model: str = "qwen3-embedding:0.6b"



class IndexRequest(BaseModel):
    repo_path: str = "test_repo"


# ---------------------------------------------------------------------------
# Conversational Query Rewriter
# ---------------------------------------------------------------------------

def rewrite_conversational_query(
    messages: list[ChatMessage],
    model: str = "qwen3:4b",
) -> str:

    """
    Rewrite the user's latest query to resolve coreferences (e.g. 'it', 'this function')
    using previous chat history into an explicit entity query for vector/graph retrieval.
    """
    if len(messages) <= 1:
        return messages[-1].content

    # Build concise history string
    history_summary = []
    for msg in messages[:-1][-4:]:  # last 4 turns
        history_summary.append(f"{msg.role.upper()}: {msg.content[:200]}")

    latest_prompt = messages[-1].content

    rewrite_prompt = (
        "Given the following conversation history between a user and a Codebase AI, "
        "rewrite the user's LATEST QUESTION into a standalone, explicit search query "
        "that names the specific code entities (functions, classes, files) being referenced. "
        "Do not answer the question — only return the standalone rewritten query.\n\n"
        f"CONVERSATION HISTORY:\n" + "\n".join(history_summary) + "\n\n"
        f"LATEST QUESTION: {latest_prompt}\n\n"
        "STANDALONE REWRITTEN QUERY:"
    )

    try:
        res = ollama.generate(model=model, prompt=rewrite_prompt)
        rewritten = res.get("response", "").strip()
        logger.info(f"Query Rewriter: '{latest_prompt}' → '{rewritten}'")
        return rewritten if rewritten else latest_prompt
    except Exception as exc:
        logger.warning(f"Query rewriter failed: {exc}. Using raw prompt.")
        return latest_prompt


# ---------------------------------------------------------------------------
# Streaming Logic
# ---------------------------------------------------------------------------

async def event_generator(
    req: ChatStreamRequest,
) -> AsyncGenerator[str, None]:
    """Generate Server-Sent Events (SSE) for real-time LLM streaming."""
    latest_user_msg = req.messages[-1].content if req.messages else ""

    # 1. Rewrite Query for Conversational Memory
    search_query = rewrite_conversational_query(req.messages, model=req.model_name)

    # Yield status event
    yield f"data: {json.dumps({'type': 'status', 'content': f'Searching Graph for: {search_query}'})}\n\n"

    # 2. Retrieve Graph Context from Neo4j
    try:
        driver = get_driver()
        context_str, seed_nodes, metrics = retrieve_subgraph_context(
            query_text=search_query,
            driver=driver,
            embed_model=req.embed_model,
        )
    except Exception as exc:
        logger.error(f"Retrieval failed: {exc}")
        context_str = f"*(Graph Retrieval Error: {exc})*"
        seed_nodes = []
        metrics = {"total_retrieval_ms": 0.0}

    yield f"data: {json.dumps({'type': 'metrics', 'data': metrics, 'seed_nodes': seed_nodes, 'context': context_str})}\n\n"

    # 3. Build Full Messages Array for Ollama
    system_prompt = (
        "You are an expert Codebase Intelligence Assistant. Answer the user's question "
        "using the provided Knowledge Graph context. Be direct, precise, and concise. "
        "Explain structural relationships, caller chains, and downstream impacts clearly."
    )

    formatted_user_prompt = f"{context_str}\n\n--- USER QUESTION ---\n{latest_user_msg}"

    ollama_messages = [{"role": "system", "content": system_prompt}]
    # Add history
    for msg in req.messages[:-1]:
        ollama_messages.append({"role": msg.role, "content": msg.content})
    ollama_messages.append({"role": "user", "content": formatted_user_prompt})

    # 4. Stream LLM Tokens
    try:
        stream = ollama.chat(model=req.model_name, messages=ollama_messages, stream=True)
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
    except Exception as exc:
        logger.error(f"LLM Stream Error: {exc}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    # Signal completion
    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/chat/stream")
async def chat_stream(req: ChatStreamRequest):
    """SSE Streaming Endpoint for Conversational Chat."""
    return StreamingResponse(
        event_generator(req),
        media_type="text/event-stream",
    )


@app.post("/api/index")
async def index_repo(req: IndexRequest):
    """Ingest and load repository into Neo4j graph."""
    from ingestion.pipeline import run_ingestion
    from graph.loader import load_parsed_repo_into_graph

    try:
        parse_res = run_ingestion(req.repo_path)
        driver = get_driver()
        load_parsed_repo_into_graph(parse_res, driver, generate_embeddings=True)
        return {
            "status": "success",
            "nodes": parse_res.node_count(),
            "edges": parse_res.edge_count(),
        }
    except Exception as exc:
        logger.error(f"Indexing error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/sessions")
async def list_sessions():
    """List all saved local chat session IDs."""
    sessions = []
    for file in CHATS_DIR.glob("*.json"):
        sessions.append(file.stem)
    return {"sessions": sorted(sessions, reverse=True)}


@app.get("/api/health")
async def health_check():
    """Check Neo4j and local system health status."""
    neo4j_status = check_connection()
    return {
        "status": "online" if neo4j_status else "degraded",
        "neo4j": neo4j_status,
        "ollama": True,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

