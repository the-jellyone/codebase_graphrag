"""
AgentState — the single data contract passed between all agent nodes.

Nothing outside of state.py defines what lives on the state object.
Nodes read from it and return updated copies — no node calls another directly.
"""

from __future__ import annotations
from typing import List
from typing_extensions import TypedDict


class ToolCall(TypedDict):
    tool: str           # tool name from TOOL_REGISTRY
    args: dict          # args passed to the tool
    result: dict        # raw result returned by the tool (empty until Executor runs)


class AgentState(TypedDict):
    question: str               # original user question, never mutated
    repo_id: str                # repo_id scoping all graph queries
    run_id: str                 # unique run identifier for logging
    tool_calls: List[ToolCall]  # full history of {tool, args, result}
    missing: str                # Synthesizer's gap report — what's still needed
    iterations: int             # how many Orchestrator → Executor → Synthesizer loops completed
    final_answer: str           # written by Synthesizer when is_complete = True
    is_complete: bool           # True = exit graph, False = loop back to Orchestrator
    is_partial: bool            # True = iteration cap hit, answer may be incomplete
    highlighted_nodes: List[str]  # node names/IDs relevant to this answer (for KG panel)
