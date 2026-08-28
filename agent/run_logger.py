"""
Run Logger — saves AgentState to disk after each major node transition.

One file per step, one folder per run.
The runs/ folder is gitignored — local execution data only.

File layout:
  runs/
  └── <run_id>/
      ├── 00_init.json
      ├── 01_orchestrator.json
      ├── 02_executor.json
      ├── 03_synthesizer.json
      └── final.json
"""

import json
import time
from pathlib import Path
from typing import Any

RUNS_DIR = Path(__file__).parent.parent / "runs"


def save_run_state(run_id: str, step: int, node_name: str, state: Any) -> None:
    """Serialize AgentState to runs/<run_id>/<step>_<node>.json."""
    folder = RUNS_DIR / run_id
    folder.mkdir(parents=True, exist_ok=True)

    filename = f"{step:02d}_{node_name}.json"
    path = folder / filename

    with open(path, "w") as f:
        json.dump(state, f, indent=2, default=str)


def save_final_run(run_id: str, state: Any, wall_time_seconds: float) -> None:
    """Write final.json with full run summary + metadata."""
    folder = RUNS_DIR / run_id
    folder.mkdir(parents=True, exist_ok=True)

    summary = {
        "run_id": run_id,
        "question": state.get("question"),
        "iterations": state.get("iterations"),
        "is_complete": state.get("is_complete"),
        "final_answer": state.get("final_answer"),
        "tool_calls": state.get("tool_calls"),
        "wall_time_seconds": round(wall_time_seconds, 3),
        "tools_used": [tc["tool"] for tc in state.get("tool_calls", [])],
    }

    with open(folder / "final.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)


def make_run_id(question: str) -> str:
    """Generate a unique run ID from timestamp + question hash."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    q_hash = hex(abs(hash(question)))[2:8]
    return f"{ts}_{q_hash}"
