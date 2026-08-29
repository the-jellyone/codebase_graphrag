"""
Hybrid Graph RAG Retriever.

Combines native Neo4j vector search with multi-hop Cypher graph traversals
to retrieve structured relational code context for local LLMs.
All retrieval is scoped by repo_id for multi-repo isolation.
"""

from __future__ import annotations
import time
from typing import Any, Optional
from neo4j import Driver
import ollama
from loguru import logger

from graph.queries import (
    vector_search_functions,
    vector_search_classes,
    get_subgraph_around_nodes,
)
from config import OLLAMA_EMBED_MODEL


def get_query_embedding(query_text: str, model: str = OLLAMA_EMBED_MODEL) -> list[float]:
    """Generate a vector embedding for a user query via local Ollama."""
    response = ollama.embeddings(model=model, prompt=query_text)
    return response["embedding"]


def retrieve_subgraph_context(
    query_text: str,
    driver: Driver,
    embed_model: str = OLLAMA_EMBED_MODEL,
    top_k: int = 3,
    hops: int = 2,
    repo_id: str = "",
) -> tuple[str, list[dict[str, Any]], dict[str, float]]:
    """
    Execute Hybrid Graph RAG Retrieval scoped to a repo_id:
    1. Embed user query using 0.6B embedding model
    2. Perform vector search in Neo4j to find top-k seed nodes (filtered by repo_id)
    3. Perform Cypher traversal around seed nodes to extract multi-hop subgraph
    4. Format retrieved subgraph into structured text context

    Returns:
        (context_markdown, seed_nodes_list, timing_metrics_dict)
    """
    metrics: dict[str, float] = {}

    # 1. Embed Query
    t0 = time.perf_counter()
    query_vec = get_query_embedding(query_text, model=embed_model)
    t1 = time.perf_counter()
    metrics["embed_ms"] = round((t1 - t0) * 1000, 2)

    # 2. Vector Search (Seed Nodes) — scoped to repo_id
    t2 = time.perf_counter()
    seed_funcs = vector_search_functions(driver, query_vec, top_k=top_k, repo_id=repo_id)
    seed_classes = vector_search_classes(driver, query_vec, top_k=top_k, repo_id=repo_id)
    t3 = time.perf_counter()
    metrics["vector_search_ms"] = round((t3 - t2) * 1000, 2)

    seed_nodes = seed_funcs + seed_classes
    if not seed_nodes:
        return "No relevant code entities found in Knowledge Graph.", [], metrics

    seed_ids = [n["id"] for n in seed_nodes]

    # 3. Graph Traversal (Multi-hop Subgraph) — scoped to repo_id
    t4 = time.perf_counter()
    subgraph_edges = get_subgraph_around_nodes(driver, seed_ids, hops=hops, repo_id=repo_id)
    t5 = time.perf_counter()
    metrics["graph_traversal_ms"] = round((t5 - t4) * 1000, 2)
    metrics["total_retrieval_ms"] = round((t5 - t0) * 1000, 2)

    # 4. Context Serialization
    context_str = _format_subgraph_context(seed_nodes, subgraph_edges)

    return context_str, seed_nodes, metrics


def _format_subgraph_context(
    seed_nodes: list[dict[str, Any]],
    subgraph_edges: list[dict[str, Any]],
) -> str:
    """Format seed nodes and traversed graph relationships into Markdown for LLM prompt."""
    lines = ["### Retrieved Codebase Knowledge Graph Context\n"]

    lines.append("#### Primary Seed Entities:")
    for node in seed_nodes:
        lines.append(f"- **{node['name']}** (`{node['file']}`)")
        if node.get("docstring"):
            lines.append(f"  *Docstring:* {node['docstring']}")
        if node.get("source_code"):
            lines.append(f"  ```python\n{node['source_code'][:300]}...\n  ```")

    lines.append("\n#### Graph Relationships & Dependencies:")
    if subgraph_edges:
        seen_rels = set()
        for edge in subgraph_edges:
            rel_str = f"- `{edge['source_name']}` -[:{edge['rel_type']}]-> `{edge['target_name']}` (Target file: `{edge['target_id'].split('::')[0]}`)"
            if rel_str not in seen_rels:
                seen_rels.add(rel_str)
                lines.append(rel_str)
    else:
        lines.append("- No extended graph relationships found.")

    return "\n".join(lines)
