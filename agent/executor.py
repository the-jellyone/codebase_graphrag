"""
Executor Node

Deterministic node — no LLM call.
Dispatches the last tool call in state["tool_calls"] to the appropriate
function in TOOL_REGISTRY, writes the result back, and saves state.

Zero tool-specific logic lives here.
Adding a new tool = zero changes to this file.
"""

from agent.state import AgentState
from agent.tools import TOOL_REGISTRY
from agent.run_logger import save_run_state


def executor_node(state: AgentState) -> AgentState:
    step = len(state["tool_calls"]) * 2  # step index for logging

    if not state["tool_calls"]:
        # Should never happen — Orchestrator always runs first
        return {**state, "tool_calls": []}

    # The last entry was added by Orchestrator with an empty result
    tool_calls = list(state["tool_calls"])
    last = dict(tool_calls[-1])

    tool_name = last["tool"]
    tool_args = dict(last.get("args", {}))
    
    # Inject repo_id from state if available and not explicitly provided in args
    if state.get("repo_id") and not tool_args.get("repo_id"):
        tool_args["repo_id"] = state["repo_id"]

    if tool_name not in TOOL_REGISTRY:
        last["result"] = {
            "error": f"Unknown tool '{tool_name}'. Valid tools: {list(TOOL_REGISTRY.keys())}"
        }
    else:
        fn = TOOL_REGISTRY[tool_name]
        try:
            last["result"] = fn(tool_args)
        except Exception as e:
            last["result"] = {"error": f"Tool execution raised an exception: {e}"}

    tool_calls[-1] = last

    new_state: AgentState = {
        **state,
        "tool_calls": tool_calls,
    }

    save_run_state(state["run_id"], step, "executor", new_state)
    return new_state
