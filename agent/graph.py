"""
Agent Graph — wires the 3 nodes with LangGraph conditional edges.

Topology:
  START → Orchestrator → Executor → Synthesizer
                 ↑                       |
                 └── (if incomplete) ────┘
                           ↓ (if complete or cap hit)
                          END

Entry point: run_agent(question: str, repo_id: str) -> dict
"""

import time
from langgraph.graph import StateGraph, END

from agent.state import AgentState
from agent.orchestrator import orchestrator_node
from agent.executor import executor_node
from agent.synthesizer import synthesizer_node
from agent.run_logger import make_run_id, save_run_state, save_final_run


def _should_continue(state: AgentState) -> str:
    """Conditional edge: loop to Orchestrator or exit to END."""
    if state.get("is_complete", False):
        return END
    return "orchestrator"


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("executor", executor_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.set_entry_point("orchestrator")
    graph.add_edge("orchestrator", "executor")
    graph.add_edge("executor", "synthesizer")
    graph.add_conditional_edges("synthesizer", _should_continue)

    return graph.compile()


# Compiled graph — built once at import time
_GRAPH = _build_graph()


def run_agent(question: str, repo_id: str = "") -> dict:
    """
    Run the agent on a question and return a structured result dict.

    Args:
        question: Natural language question about the indexed codebase.
        repo_id:  Repo identifier — scopes all graph queries to this repo.

    Returns:
        dict with keys:
            answer (str): Final markdown-formatted answer.
            trace (list): List of {tool, args} dicts for the reasoning trace.
            is_partial (bool): True if iteration cap was hit.
            highlighted_nodes (list): Node names relevant to this answer.
    """
    run_id = make_run_id(question)
    start_time = time.time()

    initial_state: AgentState = {
        "question": question,
        "repo_id": repo_id,
        "run_id": run_id,
        "tool_calls": [],
        "missing": "",
        "iterations": 0,
        "final_answer": "",
        "is_complete": False,
        "is_partial": False,
        "highlighted_nodes": [],
    }

    save_run_state(run_id, 0, "init", initial_state)

    final_state = _GRAPH.invoke(initial_state)

    wall_time = time.time() - start_time
    save_final_run(run_id, final_state, wall_time)

    # Build reasoning trace from tool_calls (tool name + args only, not results)
    trace = [
        {"tool": tc["tool"], "args": tc.get("args", {})}
        for tc in final_state.get("tool_calls", [])
    ]

    return {
        "answer": final_state.get("final_answer", "Agent did not produce a final answer."),
        "trace": trace,
        "is_partial": final_state.get("is_partial", False),
        "highlighted_nodes": final_state.get("highlighted_nodes", []),
    }
