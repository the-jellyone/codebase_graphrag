"""
Pydantic models for parsed code graph entities.

These are the core data contracts that flow between every stage of the pipeline:
  parser → graph builder → embedder → retriever

Every node has a unique `id` (file path + name) so Neo4j and ChromaDB can
reference the same entity without collision.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


# ---------------------------------------------------------------------------
# Node Types
# ---------------------------------------------------------------------------

class NodeType(str, Enum):
    """Mirrors the KG schema node labels from context.md."""
    FUNCTION  = "Function"
    CLASS     = "Class"
    MODULE    = "Module"
    EXCEPTION = "Exception"
    CONFIG    = "Config"


class EdgeType(str, Enum):
    """Mirrors the KG schema edge types from context.md."""
    CALLS      = "CALLS"
    IMPORTS    = "IMPORTS"
    INHERITS   = "INHERITS"
    RAISES     = "RAISES"
    HAS_METHOD = "HAS_METHOD"
    READS      = "READS"
    CONTAINS   = "CONTAINS"


# ---------------------------------------------------------------------------
# Node Models
# ---------------------------------------------------------------------------

class ParsedNode(BaseModel):
    """
    A single extracted code entity (function, class, module, etc.).

    `id` is constructed as "<file_path>::<name>" to be globally unique
    across the entire repo so Neo4j and ChromaDB can share the same key.
    """
    model_config = ConfigDict(use_enum_values=True)

    id:          str                  # e.g. "backend/services/user_service.py::create_user"
    type:        NodeType
    name:        str                  # e.g. "create_user"
    file:        str                  # relative path from repo root
    line:        Optional[int] = None # start line number
    docstring:   Optional[str] = None
    source_code: Optional[str] = None # full source text of the node


# ---------------------------------------------------------------------------
# Edge Models
# ---------------------------------------------------------------------------

class ParsedEdge(BaseModel):
    """
    A directed relationship between two ParsedNodes.

    `source` and `target` are node IDs (same format as ParsedNode.id).
    `properties` carries any extra metadata (e.g., the config key being read).
    """
    model_config = ConfigDict(use_enum_values=True)

    source:     str
    target:     str
    type:       EdgeType
    properties: dict = Field(default_factory=dict)



# ---------------------------------------------------------------------------
# Top-level Parse Result
# ---------------------------------------------------------------------------

class ParseResult(BaseModel):
    """
    Full output of a repo parse run.

    This is what gets serialised to `data/parsed.json` and then consumed
    by the graph builder and embedder.
    """
    repo_path:  str
    nodes:      list[ParsedNode] = Field(default_factory=list)
    edges:      list[ParsedEdge] = Field(default_factory=list)

    # Quick stats helpers
    def node_count(self) -> int:
        return len(self.nodes)

    def edge_count(self) -> int:
        return len(self.edges)

    def nodes_by_type(self, node_type: NodeType) -> list[ParsedNode]:
        return [n for n in self.nodes if n.type == node_type.value]
