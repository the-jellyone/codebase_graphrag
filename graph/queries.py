"""
Cypher query library for multi-hop graph traversals and relational reasoning.

Used by both the Graph RAG Retriever and the LangGraph Agent tools.
"""

from __future__ import annotations
from typing import Any, Optional
from neo4j import Driver
from loguru import logger

from graph.schema import FUNCTION_VECTOR_INDEX_NAME, CLASS_VECTOR_INDEX_NAME


# ---------------------------------------------------------------------------
# Vector Search Queries
# ---------------------------------------------------------------------------

def vector_search_functions(
    driver: Driver,
    query_vector: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Search for the top-k most similar Function nodes using Neo4j's native vector index."""
    query = f"""
    CALL db.index.vector.queryNodes('{FUNCTION_VECTOR_INDEX_NAME}', $top_k, $query_vector)
    YIELD node, score
    RETURN node.id AS id,
           node.name AS name,
           node.file AS file,
           node.line AS line,
           node.docstring AS docstring,
           node.source_code AS source_code,
           score
    ORDER BY score DESC
    """
    with driver.session() as session:
        result = session.run(query, {"top_k": top_k, "query_vector": query_vector})
        return [record.data() for record in result]


def vector_search_classes(
    driver: Driver,
    query_vector: list[float],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Search for the top-k most similar Class nodes using Neo4j's native vector index."""
    query = f"""
    CALL db.index.vector.queryNodes('{CLASS_VECTOR_INDEX_NAME}', $top_k, $query_vector)
    YIELD node, score
    RETURN node.id AS id,
           node.name AS name,
           node.file AS file,
           node.line AS line,
           node.docstring AS docstring,
           score
    ORDER BY score DESC
    """
    with driver.session() as session:
        result = session.run(query, {"top_k": top_k, "query_vector": query_vector})
        return [record.data() for record in result]


# ---------------------------------------------------------------------------
# Graph Traversal Queries
# ---------------------------------------------------------------------------

def get_call_chain(
    driver: Driver,
    start_func_id: str,
    max_depth: int = 4,
) -> list[dict[str, Any]]:
    """Trace forward execution/call chains originating from a function."""
    query = f"""
    MATCH path = (start:Function {{id: $start_id}})-[:CALLS*1..{max_depth}]->(target:Function)
    RETURN [node in nodes(path) | node.name] AS call_chain,
           [node in nodes(path) | node.id] AS node_ids,
           length(path) AS depth
    ORDER BY depth ASC
    """
    with driver.session() as session:
        result = session.run(query, {"start_id": start_func_id})
        return [record.data() for record in result]


def get_upstream_callers(
    driver: Driver,
    target_func_id: str,
    max_depth: int = 4,
) -> list[dict[str, Any]]:
    """Find all functions that directly or indirectly call the target function."""
    query = f"""
    MATCH path = (caller:Function)-[:CALLS*1..{max_depth}]->(target:Function {{id: $target_id}})
    RETURN [node in nodes(path) | node.name] AS caller_chain,
           [node in nodes(path) | node.id] AS node_ids,
           length(path) AS depth
    ORDER BY depth ASC
    """
    with driver.session() as session:
        result = session.run(query, {"target_id": target_func_id})
        return [record.data() for record in result]


def get_subgraph_around_nodes(
    driver: Driver,
    seed_node_ids: list[str],
    hops: int = 2,
) -> list[dict[str, Any]]:
    """
    Extract a multi-hop subgraph around seed nodes.
    Returns all traversed relationships and connected entities.
    """
    query = f"""
    MATCH (seed {{id: $seed_ids}})
    MATCH path = (seed)-[r*1..{hops}]-(connected)
    UNWIND relationships(path) AS rel
    WITH DISTINCT startNode(rel) AS src, type(rel) AS rel_type, endNode(rel) AS tgt
    RETURN src.id AS source_id,
           labels(src)[0] AS source_type,
           src.name AS source_name,
           rel_type,
           tgt.id AS target_id,
           labels(tgt)[0] AS target_type,
           tgt.name AS target_name
    """
    with driver.session() as session:
        result = session.run(query, {"seed_ids": seed_node_ids})
        return [record.data() for record in result]


def get_impact_analysis(
    driver: Driver,
    node_id: str,
) -> dict[str, Any]:
    """
    Comprehensive impact analysis:
    - Upstream callers (what breaks)
    - Downstream calls
    - Exceptions raised
    - Config read dependencies
    """
    query = """
    MATCH (n {id: $node_id})
    OPTIONAL MATCH (caller:Function)-[:CALLS]->(n)
    OPTIONAL MATCH (n)-[:CALLS]->(callee:Function)
    OPTIONAL MATCH (n)-[:RAISES]->(exc:Exception)
    OPTIONAL MATCH (n)-[:READS]->(cfg:Config)
    RETURN n.id AS target_id,
           n.name AS target_name,
           collect(DISTINCT caller.id) AS upstream_callers,
           collect(DISTINCT callee.id) AS downstream_callees,
           collect(DISTINCT exc.name) AS exceptions_raised,
           collect(DISTINCT cfg.name) AS configs_read
    """
    with driver.session() as session:
        result = session.run(query, {"node_id": node_id})
        record = result.single()
        return record.data() if record else {}
