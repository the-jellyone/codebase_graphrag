"""
Batch Knowledge Graph loader for Neo4j.

Reads ParseResult, generates vector embeddings for code nodes,
and loads all nodes and relationships into Neo4j using transactional batch UNWIND queries.
All nodes and edges are tagged with repo_id for multi-repo isolation.
"""

from __future__ import annotations
from typing import Any, Optional
from neo4j import Driver, Query
from loguru import logger

from ingestion.models import ParseResult, ParsedNode, ParsedEdge, NodeType, EdgeType
from embeddings.generator import OllamaEmbeddingGenerator
from graph.schema import setup_schema


def load_parsed_repo_into_graph(
    result: ParseResult,
    driver: Driver,
    repo_id: str = "",
    embedder: Optional[OllamaEmbeddingGenerator] = None,
    generate_embeddings: bool = True,
    batch_size: int = 100,
) -> None:
    """
    Full ingestion pipeline into Neo4j:
      1. Generates vector embeddings for Functions and Classes
      2. Initializes schema constraints and vector indexes
      3. Loads all nodes grouped by label in batches (tagged with repo_id)
      4. Loads all edges grouped by relationship type in batches
    """
    logger.info("=" * 60)
    logger.info(f"Loading repo graph into Neo4j: {result.repo_path} (repo_id={repo_id!r})")
    logger.info("=" * 60)

    # Use repo_path as fallback repo_id if none given
    effective_repo_id = repo_id or result.repo_path

    # 1. Embeddings
    dim = 1024
    if generate_embeddings:
        gen = embedder or OllamaEmbeddingGenerator()
        try:
            gen.embed_nodes(result.nodes)
            dim = gen.get_dimension()
        except Exception as exc:
            logger.warning(f"Embedding generation failed or Ollama not reachable: {exc}. Proceeding without vectors.")

    # 2. Schema Setup
    setup_schema(driver, embedding_dimension=dim)

    # 3. Load Nodes
    _load_nodes(result.nodes, driver, repo_id=effective_repo_id, batch_size=batch_size)

    # 4. Load Edges
    _load_edges(result.edges, driver, repo_id=effective_repo_id, batch_size=batch_size)

    logger.success(
        f"Graph load complete! Ingested {result.node_count()} nodes and {result.edge_count()} edges "
        f"for repo_id={effective_repo_id!r}."
    )


# ---------------------------------------------------------------------------
# Node Ingestion
# ---------------------------------------------------------------------------

def _load_nodes(
    nodes: list[ParsedNode],
    driver: Driver,
    repo_id: str = "",
    batch_size: int = 100,
) -> None:
    """Group nodes by label and insert them in batches using UNWIND + MERGE.
    Matches by unique id and sets repo_id and all properties."""
    grouped: dict[str, list[dict[str, Any]]] = {}

    for node in nodes:
        label = node.type
        props: dict[str, Any] = {
            "id": node.id,
            "name": node.name,
            "file": node.file,
            "repo_id": repo_id,
        }
        if node.line is not None:
            props["line"] = node.line
        if node.docstring is not None:
            props["docstring"] = node.docstring
        if node.source_code is not None:
            props["source_code"] = node.source_code
        if node.embedding is not None:
            props["embedding"] = node.embedding
        if node.file_hash is not None:
            props["file_hash"] = node.file_hash

        grouped.setdefault(label, []).append(props)

    with driver.session() as session:
        for label, batch_list in grouped.items():
            for i in range(0, len(batch_list), batch_size):
                chunk = batch_list[i : i + batch_size]
                query = f"""
                UNWIND $batch AS data
                MERGE (n:{label} {{id: data.id}})
                SET n += data
                """
                session.run(Query(text=query), {"batch": chunk})
            logger.debug(f"Inserted {len(batch_list)} nodes of type ':{label}' for repo_id={repo_id!r}")


# ---------------------------------------------------------------------------
# Edge Ingestion
# ---------------------------------------------------------------------------

def _load_edges(
    edges: list[ParsedEdge],
    driver: Driver,
    repo_id: str = "",
    batch_size: int = 100,
) -> None:
    """Group edges by type and insert them in batches using UNWIND + MERGE.
    Matches source and target flexibly by exact ID, suffix, or name within the same repo."""
    grouped: dict[str, list[dict[str, Any]]] = {}

    for edge in edges:
        rel_type = edge.type
        props = dict(edge.properties)
        props["repo_id"] = repo_id
        # Clean up prefix hints if present
        clean_target = edge.target.replace("ts_call::", "").replace("config::", "")
        clean_source = edge.source

        grouped.setdefault(rel_type, []).append({
            "source": clean_source,
            "target": clean_target,
            "repo_id": repo_id,
            "props": props,
        })

    with driver.session() as session:
        for rel_type, batch_list in grouped.items():
            for i in range(0, len(batch_list), batch_size):
                chunk = batch_list[i : i + batch_size]
                query = f"""
                UNWIND $batch AS data
                MATCH (s)
                WHERE (s.id = data.source OR s.name = data.source OR s.id ENDS WITH ("::" + data.source))
                  AND (data.repo_id = "" OR s.repo_id = data.repo_id OR s.repo_id IS NULL)
                WITH data, s
                MATCH (t)
                WHERE (t.id = data.target OR t.name = data.target OR t.id ENDS WITH ("::" + data.target))
                  AND (data.repo_id = "" OR t.repo_id = data.repo_id OR t.repo_id IS NULL)
                MERGE (s)-[r:{rel_type}]->(t)
                SET r += data.props
                """
                try:
                    session.run(Query(text=query), {"batch": chunk})
                except Exception as exc:
                    logger.warning(f"Failed to insert batch of [:{rel_type}] edges: {exc}")
            logger.debug(f"Inserted edges of type '[:{rel_type}]' for repo_id={repo_id!r}")
