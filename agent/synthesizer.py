"""
Synthesizer Node

LLM node. Judges whether accumulated tool results are sufficient to answer the question.

  - COMPLETE  → sets is_complete=True, writes final_answer.
  - INCOMPLETE → sets missing (gap description), loops back to Orchestrator.
  - CAP HIT (iterations >= 3) → answers with explicit caveat, sets is_partial=True.
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
    cap = data.get("cap_exceeded", {})
    if cap:
        trigger = cap.get("trigger", "iterations >= 3")
        lines.append(f"\n## Iteration Cap (triggers at {trigger})")
        lines.append(cap.get("rule", "Synthesize best answer."))
        if "guidance" in cap:
            lines.append(f"\nGuidance: {cap['guidance'].strip()}")
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
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    idx = raw.find("{")
    while idx != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[idx:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = raw.find("{", idx + 1)

    raise ValueError(f"No JSON found in synthesizer output: {raw[:200]}")


def _collect_highlighted_nodes(tool_calls: list) -> list[str]:
    """Extract node names and file names touched during tool calls for KG panel highlighting."""
    highlighted = set()
    for tc in tool_calls:
        result = tc.get("result", {})
        args = tc.get("args", {})

        # Extract from args
        for key in ("node_id", "file_path", "query"):
            val = args.get(key, "")
            if val:
                # Extract just the name part (after ::)
                name = val.split("::")[-1] if "::" in val else val
                highlighted.add(name)

        # Extract from seed_nodes in retrieval results
        seed_nodes = result.get("seed_nodes", [])
        for n in seed_nodes:
            if isinstance(n, dict):
                highlighted.add(n.get("name", "") or "")
                fname = n.get("file", "")
                if fname:
                    highlighted.add(fname.split("/")[-1])  # basename

        # Extract from chain results
        for key in ("upstream_callers", "downstream_callees", "call_chain", "caller_chain"):
            items = result.get(key, [])
            for item in items:
                if isinstance(item, str) and "::" in item:
                    highlighted.add(item.split("::")[-1])

    return [h for h in highlighted if h]  # filter empty strings


def synthesizer_node(state: AgentState) -> AgentState:
    iterations = state.get("iterations", 0) + 1
    step = len(state["tool_calls"]) * 2 + 1  # step index for logging

    tool_results_str = _format_tool_results(state["tool_calls"])

    if iterations >= MAX_ITERATIONS:
        user_message = (
            f"Question: {state['question']}\n\n"
            f"Iteration: {iterations} of {MAX_ITERATIONS} (FINAL ITERATION)\n\n"
            f"All tool results so far:\n{tool_results_str}\n\n"
            "This is the final iteration. You MUST mark \"is_complete\": true and write a thorough, detailed markdown answer in the \"final_answer\" field summarizing all findings. Respond with JSON only."
        )
    else:
        user_message = (
            f"Question: {state['question']}\n\n"
            f"Iteration: {iterations} of {MAX_ITERATIONS}\n\n"
            f"All tool results so far:\n{tool_results_str}\n\n"
            "Judge whether this is sufficient to answer the question. If complete, provide the full answer in \"final_answer\". Respond with JSON only."
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
        is_complete = bool(parsed.get("is_complete", False) or parsed.get("is_sufficient", False))
        final_answer = parsed.get("final_answer") or parsed.get("answer") or parsed.get("analysis") or parsed.get("reason") or ""
        missing = parsed.get("missing") or parsed.get("gap") or ""
    except (ValueError, json.JSONDecodeError):
        # Clean up any raw JSON braces if present
        is_complete = True
        final_answer = re.sub(r'^\s*\{[\s\S]*"final_answer"\s*:\s*"([^"]+)"[\s\S]*\}\s*$', r'\1', raw)
        missing = ""

    is_partial = False

    # Enforce iteration cap — accept model's best answer and mark as partial
    if iterations >= MAX_ITERATIONS and not is_complete:
        is_complete = True
        is_partial = True
        missing = ""

    # Ensure a rich markdown answer is always synthesized from the tool results
    if is_complete and (not final_answer or len(final_answer.strip()) < 40 or final_answer.startswith("{")):
        try:
            synth_resp = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert codebase intelligence assistant. Using the gathered knowledge graph context and tool results, "
                            "provide a comprehensive, clear, and well-structured markdown answer to the user's question. Focus on architectural flows, functions, classes, and code structure."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Question: {state['question']}\n\nRetrieved Codebase Context:\n{tool_results_str}",
                    },
                ],
                options={"temperature": 0.2},
            )
            final_answer = synth_resp["message"]["content"]
        except Exception:
            if not final_answer:
                final_answer = missing or "Based on the codebase analysis, here is what was found from the knowledge graph."

    # Collect highlighted nodes from all tool calls
    highlighted_nodes = _collect_highlighted_nodes(state["tool_calls"])

    new_state: AgentState = {
        **state,
        "iterations": iterations,
        "is_complete": is_complete,
        "final_answer": final_answer,
        "missing": missing,
        "is_partial": is_partial,
        "highlighted_nodes": highlighted_nodes,
    }

    save_run_state(state["run_id"], step, "synthesizer", new_state)
    return new_state
