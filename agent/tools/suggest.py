"""
Tool: suggest_fix

Text-only diagnosis and recommendation for a code issue.
No file writes. Returns a structured suggestion referencing specific
nodes, functions, or patterns that should be addressed.

This is a pure generation tool — it calls the LLM with the provided
context and produces an actionable, honest recommendation.
"""

import ollama
from config import OLLAMA_LLM_MODEL

OLLAMA_MODEL = OLLAMA_LLM_MODEL

_SYSTEM_PROMPT = """You are a senior software engineer reviewing a codebase.
Your task is to diagnose a code quality issue and suggest a concrete fix.

Rules:
- Be specific — reference exact function names, files, and line numbers when known.
- Be honest — if you can't determine a fix without more context, say so.
- Never suggest writing code you haven't seen. Describe the change, don't generate untested code.
- Keep your response concise: diagnosis (1-2 sentences), recommendation (2-4 bullet points).
- Do NOT write or modify any files. Suggestions only.
"""


def suggest_fix(args: dict) -> dict:
    """
    Generate a text-only code fix suggestion based on provided context.

    Args:
        args:
            context (str): Description of the issue + relevant code or graph context.
            node_id (str, optional): Specific node the issue relates to.

    Returns:
        dict with keys:
            suggestion (str): Diagnosis + concrete recommendations.
            node_id (str | None): Echoed from args.
            error (str | None): Set on failure.
    """
    context = args.get("context", "")
    node_id = args.get("node_id", None)

    if not context:
        return {"error": "context is required", "suggestion": "", "node_id": node_id}

    user_message = f"Context:\n{context}"
    if node_id:
        user_message += f"\n\nPrimary node under review: {node_id}"

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            options={"temperature": 0.3},
        )
        suggestion = response["message"]["content"].strip()
        return {"suggestion": suggestion, "node_id": node_id, "error": None}
    except Exception as e:
        return {"error": str(e), "suggestion": "", "node_id": node_id}
