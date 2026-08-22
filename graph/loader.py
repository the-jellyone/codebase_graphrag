"""
Batch Knowledge Graph loader for Neo4j.

Reads ParseResult, generates vector embeddings for code nodes,
and loads all nodes and relationships into Neo4j using transactional batch UNWIND queries.
"""

from __future__ import annotations
from typing import Any, Optional
from neo4j import Driver, Transaction
from loguru import logger

from ingestion.models import ParseResult, ParsedNode, ParsedEdge, NodeType, EdgeType
from embeddings.generator import OllamaEmbeddingGenerator
from graph.schema import setup_schema


def load_parsed_repo_into_graph(
    result: ParseResult,
    driver: Driver,
    embedder: Optional[OllamaEmbeddingGenerator] = None,
    generate_embeddings: bool = True,
    batch_size: int = 100,
) -> None:
    """
    Full ingestion pipeline into Neo4j:
      1. Generates vector embeddings for Functions and Classes
      2. Initializes schema constraints and vector indexes
      3. Loads all nodes grouped by label in batches
      4. Loads all edges grouped by relationship type in batches
    """
    logger.info("=" * 60)
    logger.info(f"Loading repo graph into Neo4j: {result.repo_path}")
    logger.info("=" * 60)

    # 1. Embeddings
    dim = 1536
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
    _load_nodes(result.nodes, driver, batch_size=batch_size)

    # 4. Load Edges
    _load_edges(result.edges, driver, batch_size=batch_size)

    logger.success(
        f"Graph load complete! Ingested {result.node_count()} nodes and {result.edge_count()} edges."
    )


# ---------------------------------------------------------------------------
# Node Ingestion
# ---------------------------------------------------------------------------

def _load_nodes(nodes: list[ParsedNode], driver: Driver, batch_size: int = 100) -> None:
    """Group nodes by label and insert them in batches using UNWIND + MERGE."""
    grouped: dict[str, list[dict[str, Any]]] = {}

    for node in nodes:
        label = node.type
        props: dict[str, Any] = {
            "id": node.id,
            "name": node.name,
            "file": node.file,
        }
        if node.line is not None:
            props["line"] = node.line
        if node.docstring is not None:
            props["docstring"] = node.docstring
        if node.source_code is not None:
            props["source_code"] = node.source_code
        if node.embedding is not None:
            props["embedding"] = node.embedding

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
                session.run(query, {"batch": chunk})
            logger.debug(f"Inserted {len(batch_list)} nodes of type ':{label}'")


# ---------------------------------------------------------------------------
# Edge Ingestion
# ---------------------------------------------------------------------------

def _load_edges(edges: list[ParsedEdge], driver: Driver, batch_size: int = 100) -> None:
    """Group edges by type and insert them in batches using UNWIND + MERGE."""
    grouped: dict[str, list[dict[str, Any]]] = {}

    for edge in edges:
        rel_type = edge.type
        grouped.setdefault(rel_type, []).append({
            "source": edge.source,
            "target": edge.target,
            "props": edge.properties,
        })

    with driver.session() as session:
        for rel_type, batch_list in grouped.items():
            for i in range(0, len(batch_list), batch_size):
                chunk = batch_list[i : i + batch_size]
                query = f"""
                UNWIND $batch AS data
                MATCH (s {{id: data.source}})
                MATCH (t {{id: data.target}})
                MERGE (s)-[r:{rel_type}]->(t)
                SET r += data.props
                """
                session.run(query, {"batch": chunk})
            logger.debug(f"Inserted {len(batch_list)} edges of type '[:{rel_type}]'")
