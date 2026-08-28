"""
Orchestrator Node

LLM node (qwen3:4b, thinking-enabled).
Reads the current AgentState, builds a prompt with:
  - The user's question
  - All prior tool results
  - What the Synthesizer said is still missing
Then calls the LLM and parses out {tool, args} as JSON.

System prompt is defined in agent/prompts/orchestrator.yaml and rendered at import time.
"""

import json
import re
from pathlib import Path

import yaml
import ollama

from agent.state import AgentState
from agent.run_logger import save_run_state
from config import OLLAMA_LLM_MODEL

OLLAMA_MODEL = OLLAMA_LLM_MODEL

_PROMPT_PATH = Path(__file__).parent / "prompts" / "orchestrator.yaml"


def _render_orchestrator_prompt(data: dict) -> str:
    """Render orchestrator.yaml into a system prompt string."""
    lines = []
    lines.append(f"# {data['role']}")
    lines.append(data["description"].strip())
    lines.append("")
    lines.append("## Available Tools")
    for tool in data["tools"]:
        lines.append(f"\n### {tool['name']}")
        lines.append(f"- **When**: {tool['when']}")
        lines.append(f"- **Args**: `{tool['args']}`")
        if "presets" in tool:
            lines.append("- **Presets**:")
            for preset in tool["presets"]:
                for k, v in preset.items():
                    lines.append(f"  - `{k}`: {v}")
    lines.append("\n## Decision Rules")
    for rule in data["decision_rules"]:
        lines.append(f"- {rule}")
    lines.append("\n## Output Format")
    lines.append(data["output_format"]["instruction"])
    lines.append(f"```json\n{data['output_format']['schema']}\n```")
    lines.append("\n## Context You Will Receive")
    for item in data["context_received"]:
        lines.append(f"- {item}")
    return "\n".join(lines)


_raw = yaml.safe_load(_PROMPT_PATH.read_text(encoding="utf-8"))
_SYSTEM_PROMPT = _render_orchestrator_prompt(_raw)


def _format_tool_results(tool_calls: list) -> str:
    """Render prior tool results into a readable block for the prompt."""
    if not tool_calls:
        return "None yet."
    parts = []
    for i, tc in enumerate(tool_calls, 1):
        result_str = json.dumps(tc.get("result", {}), indent=2, default=str)
        # Truncate very large results to avoid blowing context
        if len(result_str) > 3000:
            result_str = result_str[:3000] + "\n... [truncated]"
        parts.append(
            f"[Call {i}] Tool: {tc['tool']}\n"
            f"Args: {json.dumps(tc.get('args', {}))}\n"
            f"Result:\n{result_str}"
        )
    return "\n\n".join(parts)


def _extract_json(raw: str) -> dict:
    """Extract JSON from model output that may be wrapped in markdown fences or include commentary."""
    raw = raw.strip()
    # 1. Look for markdown code fence
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Extract using json.JSONDecoder.raw_decode from the first '{'
    idx = raw.find("{")
    while idx != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(raw[idx:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        idx = raw.find("{", idx + 1)

    raise ValueError(f"No valid JSON found in model output: {raw[:200]}")


def orchestrator_node(state: AgentState) -> AgentState:
    step = len(state["tool_calls"]) * 2 + 1  # step index for logging

    prior_results = _format_tool_results(state["tool_calls"])
    missing_gap = state.get("missing", "") or "No prior assessment yet — this is the first call."

    user_message = (
        f"Question: {state['question']}\n\n"
        f"Prior tool results:\n{prior_results}\n\n"
        f"What Synthesizer reported as missing: {missing_gap}\n\n"
        "Pick the next tool to call."
    )

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        options={"temperature": 0},
    )

    raw = response["message"]["content"]
    parsed = _extract_json(raw)

    tool_name = parsed.get("tool", "")
    tool_args = parsed.get("args", {})

    # Append new tool call (no result yet — Executor fills that in)
    new_tool_calls = list(state["tool_calls"]) + [
        {"tool": tool_name, "args": tool_args, "result": {}}
    ]

    new_state: AgentState = {
        **state,
        "tool_calls": new_tool_calls,
    }

    save_run_state(state["run_id"], step, "orchestrator", new_state)
    return new_state
