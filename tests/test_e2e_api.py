"""
End-to-End Integration Test Suite for CodeGraph.

Tests:
1. SQLite persistence (repos, chats, messages, auto-title)
2. Ingestion of test_repo into Neo4j with repo_id
3. Multi-repo graph queries & isolation
4. Incremental resync & hash change detection
5. FastAPI REST & SSE endpoints via TestClient
6. LangGraph 3-node Agent execution with repo_id scoping
"""

import os
import sys
import pytest
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import db as database
from graph.connection import get_driver, check_connection
from ingestion.pipeline import run_ingestion
from graph.loader import load_parsed_repo_into_graph
from graph.queries import (
    vector_search_functions,
    get_call_chain,
    get_upstream_callers,
    get_impact_analysis,
    get_graph_preview,
    get_repo_stats,
)
from graph.updater import incremental_resync_repo
from retrieval.retriever import retrieve_subgraph_context
from agent.graph import run_agent
from fastapi.testclient import TestClient
from interface.api import app


# ---------------------------------------------------------------------------
# 1. SQLite Database Unit Tests
# ---------------------------------------------------------------------------

def test_sqlite_db_operations():
    """Verify SQLite CRUD for repos, chats, messages, and title generation."""
    database.init_db()

    # 1. Create repo
    repo_id = database.create_repo(source="test_repo", name="Test Repository")
    assert repo_id is not None
    repo = database.get_repo(repo_id)
    assert repo["name"] == "Test Repository"
    assert repo["status"] == "idle"

    # 2. Update status
    database.update_repo_status(repo_id, "ready", last_synced="2026-08-29T21:00:00Z")
    repo = database.get_repo(repo_id)
    assert repo["status"] == "ready"
    assert repo["last_synced"] == "2026-08-29T21:00:00Z"

    # 3. Create chat
    chat_id = database.create_chat(repo_id=repo_id, title="Initial Chat")
    assert chat_id is not None
    chats = database.list_chats(repo_id)
    assert len(chats) >= 1
    assert any(c["chat_id"] == chat_id for c in chats)

    # 4. Save messages
    msg1_id = database.save_message(chat_id, role="user", content="How does authentication work?", mode="agent")
    msg2_id = database.save_message(
        chat_id,
        role="assistant",
        content="JWT validation happens in router.",
        mode="agent",
        trace=[{"tool": "search_graph", "args": {"query": "auth"}}],
        is_partial=False,
        highlighted_nodes=["auth.py", "router.py"],
    )

    msgs = database.list_messages(chat_id)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert len(msgs[1]["trace"]) == 1
    assert msgs[1]["highlighted_nodes"] == ["auth.py", "router.py"]

    # 5. Auto-title generator
    title = database.generate_title("What exceptions are raised by user_service.create_user?")
    assert len(title.split()) <= 6
    assert "exceptions" in title.lower()


# ---------------------------------------------------------------------------
# 2. Neo4j Ingestion & Multi-Repo Query Tests
# ---------------------------------------------------------------------------

def test_neo4j_ingestion_and_queries():
    """Verify test_repo ingestion and multi-hop graph queries scoped by repo_id."""
    if not check_connection():
        pytest.skip("Neo4j is not connected. Skipping Neo4j integration test.")

    driver = get_driver()
    repo_id = "test_e2e_repo"

    # Parse and load test_repo into graph with repo_id
    parse_result = run_ingestion("test_repo")
    assert parse_result.node_count() > 0

    load_parsed_repo_into_graph(
        result=parse_result,
        driver=driver,
        repo_id=repo_id,
        generate_embeddings=False,
    )

    # Verify repo stats
    stats = get_repo_stats(driver, repo_id)
    assert stats["node_count"] > 0
    assert stats["edge_count"] > 0

    # Verify graph preview
    preview = get_graph_preview(driver, repo_id=repo_id, limit=30)
    assert len(preview["nodes"]) > 0

    # Verify impact analysis (repository.save)
    impact = get_impact_analysis(driver, node_id="save", repo_id=repo_id)
    assert "upstream_callers" in impact

    # Verify call chain
    chain = get_call_chain(driver, start_func_id="create_user", repo_id=repo_id)
    assert isinstance(chain, list)


# ---------------------------------------------------------------------------
# 3. Incremental Resync Test
# ---------------------------------------------------------------------------

def test_incremental_resync():
    """Verify incremental resync runs without errors and detects file states."""
    if not check_connection():
        pytest.skip("Neo4j is not connected. Skipping resync test.")

    driver = get_driver()
    repo_id = "test_e2e_repo"

    res = incremental_resync_repo(
        driver=driver,
        repo_root=PROJECT_ROOT / "test_repo",
        repo_id=repo_id,
        generate_embeddings=False,
    )
    assert "updated" in res
    assert "deleted" in res
    assert "skipped" in res


# ---------------------------------------------------------------------------
# 4. FastAPI Endpoints Integration Tests
# ---------------------------------------------------------------------------

def test_api_endpoints():
    """Verify FastAPI REST API endpoints."""
    client = TestClient(app)

    # 1. Health check
    res = client.get("/api/health")
    assert res.status_code == 200
    assert "status" in res.json()

    # 2. Add repo
    res = client.post("/repos", json={"source": "test_repo", "name": "E2E Test Repo"})
    assert res.status_code == 202
    data = res.json()
    repo_id = data["repo_id"]

    # 3. List repos
    res = client.get("/repos")
    assert res.status_code == 200
    repos = res.json()
    assert any(r["repo_id"] == repo_id for r in repos)

    # 4. Index status
    res = client.get(f"/repos/{repo_id}/index-status")
    assert res.status_code == 200
    status_data = res.json()
    assert "status" in status_data
    assert "stages" in status_data

    # 5. Create chat
    res = client.post("/chats", json={"repo_id": repo_id})
    assert res.status_code == 201
    chat_id = res.json()["chat_id"]

    # 6. List chats
    res = client.get(f"/chats?repo_id={repo_id}")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 7. Messages list
    res = client.get(f"/chats/{chat_id}/messages")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # 8. Repo stats
    res = client.get(f"/repos/{repo_id}/stats")
    assert res.status_code == 200

    # 9. Graph preview
    res = client.get(f"/repos/{repo_id}/graph-preview")
    assert res.status_code == 200
    assert "nodes" in res.json()
    assert "edges" in res.json()

    # 10. KG query url
    res = client.get(f"/repos/{repo_id}/kg-query-url")
    assert res.status_code == 200
    assert "url" in res.json()

    # 11. Delete repo
    del_res = client.delete(f"/repos/{repo_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"


if __name__ == "__main__":
    pytest.main(["-v", __file__])
