"""
Synthesizer Node

LLM node (qwen3:4b, thinking-enabled).
Judges whether accumulated tool results are sufficient to answer the question.

  - COMPLETE  → sets is_complete=True, writes final_answer.
  - INCOMPLETE → sets missing (gap description), loops back to Orchestrator.
  - CAP HIT (iterations >= 3) → answers with explicit caveat, never hallucinates.
"""

import json
import re
from pathlib import Path

import ollama
import yaml

from agent.state import AgentState
from agent.run_logger import save_run_state
from config import OLLAMA_LLM_MODEL

OLLAMA_MODEL = OLLAMA_LLM_MODEL

MAX_ITERATIONS = 3

_PROMPT_PATH = Path(__file__).parent / "prompts" / "synthesizer.yaml"


def _render_synthesizer_prompt(data: dict) -> str:
    """Render synthesizer.yaml into a system prompt string."""
    lines = []
    lines.append(f"# {data['role']}")
    lines.append(data["description"].strip())
    lines.append("")
    lines.append("## Mark COMPLETE when")
    for item in data["complete_when"]:
        lines.append(f"- {item}")
    lines.append("\n## Mark INCOMPLETE when")
    for item in data["incomplete_when"]:
        lines.append(f"- {item}")
    cap = data["cap_exceeded"]
    lines.append(f"\n## Iteration Cap (triggers at iterations >= {cap['trigger'].split()[-1]})")
    lines.append(cap["rule"])
    lines.append(f"\nCaveat template: {cap['caveat_template'].strip()}")
    lines.append(f"\nRule: {cap['rule_never']}")
    lines.append("\n## Output Format")
    fmt = data["output_format"]
    lines.append(fmt["instruction"])
    lines.append(f"Complete:   `{fmt['complete']}`")
    lines.append(f"Incomplete: `{fmt['incomplete']}`")
    lines.append("\n## Answer Guidelines")
    for item in data["answer_guidelines"]:
        lines.append(f"- {item}")
    lines.append("\n## Context You Will Receive")
    for item in data["context_received"]:
        lines.append(f"- {item}")
    return "\n".join(lines)


_raw = yaml.safe_load(_PROMPT_PATH.read_text(encoding="utf-8"))
_SYSTEM_PROMPT = _render_synthesizer_prompt(_raw)


def _format_tool_results(tool_calls: list) -> str:
    """Render all tool results into a readable block."""
    if not tool_calls:
        return "No tool results yet."
    parts = []
    for i, tc in enumerate(tool_calls, 1):
        result_str = json.dumps(tc.get("result", {}), indent=2, default=str)
        if len(result_str) > 4000:
            result_str = result_str[:4000] + "\n... [truncated]"
        parts.append(
            f"[Result {i}] Tool: {tc['tool']}\n"
            f"Args: {json.dumps(tc.get('args', {}))}\n"
            f"Result:\n{result_str}"
        )
    return "\n\n".join(parts)


def _extract_json(raw: str) -> dict:
    """Extract JSON from model output, stripping markdown fences if present."""
    raw = raw.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"No JSON found in synthesizer output: {raw[:200]}")


def synthesizer_node(state: AgentState) -> AgentState:
    iterations = state.get("iterations", 0) + 1
    step = len(state["tool_calls"]) * 2 + 1  # step index for logging

    tool_results_str = _format_tool_results(state["tool_calls"])

    user_message = (
        f"Question: {state['question']}\n\n"
        f"Iteration: {iterations} of {MAX_ITERATIONS}\n\n"
        f"All tool results so far:\n{tool_results_str}\n\n"
        "Judge whether this is sufficient to answer the question. Respond with JSON only."
    )

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        options={"temperature": 0.1},
    )

    raw = response["message"]["content"]

    try:
        parsed = _extract_json(raw)
        is_complete = bool(parsed.get("is_complete", False))
        final_answer = parsed.get("final_answer", "")
        missing = parsed.get("missing", "")
    except (ValueError, json.JSONDecodeError):
        # If parsing fails, treat the raw output as the final answer
        is_complete = True
        final_answer = raw
        missing = ""

    # Enforce iteration cap — answer with caveat regardless of is_complete flag
    if iterations >= MAX_ITERATIONS and not is_complete:
        partial = final_answer or "No complete answer could be assembled from retrieved data."
        # Identify any node IDs or file paths mentioned in tool results for the caveat
        node_hints = []
        for tc in state["tool_calls"]:
            args = tc.get("args", {})
            if "node_id" in args:
                node_hints.append(args["node_id"])
            if "file_path" in args:
                node_hints.append(args["file_path"])

        hint_str = ", ".join(node_hints) if node_hints else "the relevant source files"
        final_answer = (
            f"After multiple retrieval attempts I wasn't able to find sufficient context "
            f"in the knowledge graph to fully answer this. Here's what I found: {partial}. "
            f"You may want to check {hint_str} directly."
        )
        is_complete = True
        missing = ""

    new_state: AgentState = {
        **state,
        "iterations": iterations,
        "is_complete": is_complete,
        "final_answer": final_answer,
        "missing": missing,
    }

    save_run_state(state["run_id"], step, "synthesizer", new_state)
    return new_state
