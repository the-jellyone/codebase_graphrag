"""
Formatter converting ParsedNode instances into rich contextual text for embeddings.

Why rich formatting matters:
  Flat source code embeddings miss metadata (e.g. file path, entity type, docstring context).
  By structuring the text with clear semantic boundaries, vector search can match on:
  - natural language intent (via docstrings and name)
  - structural queries (via file path and entity type)
  - signature/logic queries (via source code)
"""

from __future__ import annotations
from typing import Optional
from ingestion.models import ParsedNode, NodeType


def format_node_for_embedding(node: ParsedNode) -> str:
    """
    Format a ParsedNode into a structured text representation for embedding models.

    Example output for a Function:
      [Function] create_user
      File: backend/services/user_service.py:12
      Docstring: Create and persist a new user.
      Source:
      def create_user(name: str, email: str) -> Dict[str, Any]:
          validators.validate_email(email)
          ...
    """
    lines: list[str] = [
        f"[{node.type}] {node.name}",
        f"File: {node.file}" + (f":{node.line}" if node.line else ""),
    ]

    if node.docstring:
        lines.append(f"Docstring: {node.docstring.strip()}")

    if node.source_code:
        lines.append("Source:")
        lines.append(node.source_code.strip())

    return "\n".join(lines)


def should_embed_node(node: ParsedNode) -> bool:
    """
    Determine if a node should be vectorized in the Vector Index.
    
    Functions and Classes carry semantic behavior and are the primary targets
    for vector search seeds. Modules, Exceptions, and Configs are linked via graph relations.
    """
    return node.type in (NodeType.FUNCTION.value, NodeType.CLASS.value)
