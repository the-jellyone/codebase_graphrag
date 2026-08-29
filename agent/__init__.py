"""
Agent package — 3-node LangGraph code intelligence agent.

Public API:
    from agent import run_agent
    result = run_agent("What breaks if I change user_service.create_user?", repo_id="my-repo")
    # result = {"answer": str, "trace": list, "is_partial": bool, "highlighted_nodes": list}
"""

from agent.graph import run_agent

__all__ = ["run_agent"]
