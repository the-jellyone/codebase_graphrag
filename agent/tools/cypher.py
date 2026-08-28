"""
Tools: run_cypher, list_by_pattern

run_cypher:
  Orchestrator describes intent in natural language → tool generates Cypher
  (injecting the full schema) → executes against Neo4j.
  Silent self-repair: if execution fails, retries once with the error fed back.

list_by_pattern:
  Five structural presets wrapping run_cypher for common analysis queries.
  Orchestrator picks a preset by name — no raw Cypher needed.
"""

import json
import re
import ollama
from graph.connection import get_driver
from graph.schema_def import GRAPH_SCHEMA
from config import OLLAMA_LLM_MODEL

OLLAMA_MODEL = OLLAMA_LLM_MODEL

# ---------------------------------------------------------------------------
# Cypher generation helpers
# ---------------------------------------------------------------------------

def _build_cypher_prompt(intent: str, error_context: str = "") -> str:
    prompt = f"""You are a Neo4j Cypher expert. Generate a valid Cypher query for the following intent.

{GRAPH_SCHEMA}

Intent: {intent}
"""
    if error_context:
        prompt += f"""
The previous query attempt failed with this error:
{error_context}

Fix the Cypher query. Return ONLY the corrected Cypher — no explanation, no markdown.
"""
    else:
        prompt += "\nReturn ONLY the Cypher query — no explanation, no markdown fences."

    return prompt


def _extract_cypher(raw: str) -> str:
    """Strip markdown code fences if the model wrapped the query."""
    raw = raw.strip()
    match = re.search(r"```(?:cypher)?\s*(.*?)```", raw, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return raw


def _generate_cypher(intent: str, error_context: str = "") -> str:
    prompt = _build_cypher_prompt(intent, error_context)
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0},
    )
    return _extract_cypher(response["message"]["content"])


def _execute_cypher(cypher: str, params: dict = None) -> list:
    driver = get_driver()
    with driver.session() as session:
        result = session.run(cypher, parameters=params or {})
        return [dict(record) for record in result]


# ---------------------------------------------------------------------------
# run_cypher
# ---------------------------------------------------------------------------

def run_cypher(args: dict) -> dict:
    """
    Generate Cypher from a plain English intent and execute it against Neo4j.
    Retries once on execution failure with the error message fed back into generation.

    Args:
        args:
            intent (str): What you want to find, in plain English.

    Returns:
        dict with keys:
            records (list): Query result rows.
            cypher (str): The Cypher query that was executed.
            error (str | None): Set if both attempts failed.
    """
    intent = args.get("intent", "")
    if not intent:
        return {"error": "intent is required", "records": [], "cypher": ""}

    cypher = ""
    # First attempt
    try:
        cypher = _generate_cypher(intent)
        records = _execute_cypher(cypher)
        return {"records": records, "cypher": cypher, "error": None}
    except Exception as first_error:
        # Silent self-repair: retry once with error context
        try:
            cypher = _generate_cypher(intent, error_context=str(first_error))
            records = _execute_cypher(cypher)
            return {"records": records, "cypher": cypher, "error": None, "repaired": True}
        except Exception as second_error:
            return {
                "error": f"Cypher generation and execution failed after retry: {second_error}",
                "records": [],
                "cypher": cypher,
            }


# ---------------------------------------------------------------------------
# list_by_pattern — 5 structural presets
# ---------------------------------------------------------------------------

_PATTERN_INTENTS = {
    "no_docstring": (
        "Find all Function and Class nodes where the docstring property is null or an empty string. "
        "Return node id, name, and file. Limit to {limit}."
    ),
    "high_method_count": (
        "Find Class nodes with the most HAS_METHOD relationships. "
        "Return class id, name, file, and the count of methods. Order by method count descending. Limit to {limit}."
    ),
    "unused_function": (
        "Find Function nodes that have zero incoming CALLS relationships — nothing calls them. "
        "Return function id, name, and file. Limit to {limit}."
    ),
    "high_coupling": (
        "Find Function and Class nodes with the highest combined count of incoming and outgoing "
        "relationships of any type. Return node id, name, file, and the total edge count. "
        "Order by total descending. Limit to {limit}."
    ),
    "no_test_coverage": (
        "Find Function nodes that have no incoming CALLS relationship from any Function node "
        "whose file path contains 'test'. Return function id, name, and file. Limit to {limit}."
    ),
}

VALID_PATTERNS = list(_PATTERN_INTENTS.keys())


def list_by_pattern(args: dict) -> dict:
    """
    Run a named structural preset query against the knowledge graph.

    Args:
        args:
            pattern (str): One of: no_docstring, high_method_count, unused_function,
                           high_coupling, no_test_coverage.
            limit (int, optional): Max results to return. Default 10.

    Returns:
        dict with keys:
            records (list): Query result rows.
            pattern (str): The pattern name used.
            cypher (str): The generated Cypher.
            error (str | None): Set on failure.
    """
    pattern = args.get("pattern", "")
    limit = args.get("limit", 10)

    if pattern not in _PATTERN_INTENTS:
        return {
            "error": f"Unknown pattern '{pattern}'. Valid options: {VALID_PATTERNS}",
            "records": [],
            "pattern": pattern,
            "cypher": "",
        }

    intent = _PATTERN_INTENTS[pattern].format(limit=limit)
    result = run_cypher({"intent": intent})
    result["pattern"] = pattern
    return result
