"""
TOOL_REGISTRY — single source of truth for all registered agent tools.

Every tool has the signature: (args: dict) -> dict
Executor dispatches by name from this registry — zero tool-specific logic in the Executor.

To add a new tool:
  1. Implement it in the appropriate tools/ module.
  2. Import it here.
  3. Add it to TOOL_REGISTRY.
  That's it — Executor, Orchestrator prompts, and schema pick it up automatically.
"""

from agent.tools.retrieval import graph_rag_search
from agent.tools.cypher import run_cypher, list_by_pattern
from agent.tools.files import get_file_content
from agent.tools.impact import trace_impact, get_call_chain
from agent.tools.suggest import suggest_fix

TOOL_REGISTRY: dict = {
    "graph_rag_search": graph_rag_search,
    "run_cypher": run_cypher,
    "list_by_pattern": list_by_pattern,
    "get_file_content": get_file_content,
    "trace_impact": trace_impact,
    "get_call_chain": get_call_chain,
    "suggest_fix": suggest_fix,
}

__all__ = ["TOOL_REGISTRY"]
