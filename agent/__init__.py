"""
Agent package — 3-node LangGraph code intelligence agent.

Public API:
    from agent import run_agent
    answer = run_agent("What breaks if I change user_service.create_user?")
"""

from agent.graph import run_agent

__all__ = ["run_agent"]
