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

def _extract_name_and_module(node_id: str) -> tuple[str, str]:
    """Extract entity name and module hint from partial or formatted IDs."""
    clean_id = node_id.strip()
    if "::" in clean_id:
        parts = clean_id.split("::", 1)
        return parts[1], parts[0]
    if "." in clean_id:
        parts = clean_id.rsplit(".", 1)
        return parts[1], parts[0]
    return clean_id, ""


def get_call_chain(
    driver: Driver,
    start_func_id: str,
    max_depth: int = 4,
) -> list[dict[str, Any]]:
    """Trace forward execution/call chains originating from a function."""
    name, module = _extract_name_and_module(start_func_id)
    query = f"""
    MATCH (start:Function)
    WHERE start.id = $start_id
       OR start.id ENDS WITH ("::" + $start_id)
       OR start.name = $start_id
       OR (start.name = $name AND (start.file CONTAINS $module OR start.id CONTAINS $module))
       OR start.id CONTAINS $start_id
    WITH start LIMIT 1
    MATCH path = (start)-[:CALLS*1..{max_depth}]->(target:Function)
    RETURN [node in nodes(path) | node.name] AS call_chain,
           [node in nodes(path) | node.id] AS node_ids,
           length(path) AS depth
    ORDER BY depth ASC
    """
    with driver.session() as session:
        result = session.run(query, {"start_id": start_func_id, "name": name, "module": module})
        return [record.data() for record in result]


def get_upstream_callers(
    driver: Driver,
    target_func_id: str,
    max_depth: int = 4,
) -> list[dict[str, Any]]:
    """Find all functions that directly or indirectly call the target function."""
    name, module = _extract_name_and_module(target_func_id)
    query = f"""
    MATCH (target:Function)
    WHERE target.id = $target_id
       OR target.id ENDS WITH ("::" + $target_id)
       OR target.name = $target_id
       OR (target.name = $name AND (target.file CONTAINS $module OR target.id CONTAINS $module))
       OR target.id CONTAINS $target_id
    WITH target LIMIT 1
    MATCH path = (caller:Function)-[:CALLS*1..{max_depth}]->(target)
    RETURN [node in nodes(path) | node.name] AS caller_chain,
           [node in nodes(path) | node.id] AS node_ids,
           length(path) AS depth
    ORDER BY depth ASC
    """
    with driver.session() as session:
        result = session.run(query, {"target_id": target_func_id, "name": name, "module": module})
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
    MATCH (seed)
    WHERE seed.id IN $seed_ids
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
    - Direct & multi-hop upstream callers (what breaks)
    - Direct downstream calls
    - Exceptions raised
    - Config read dependencies
    """
    name, module = _extract_name_and_module(node_id)
    query = """
    MATCH (n)
    WHERE n.id = $node_id
       OR n.id ENDS WITH ("::" + $node_id)
       OR n.name = $node_id
       OR (n.name = $name AND (n.file CONTAINS $module OR n.id CONTAINS $module))
       OR n.id CONTAINS $node_id
    WITH n LIMIT 1
    OPTIONAL MATCH (caller:Function)-[:CALLS*1..3]->(n)
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
        result = session.run(query, {"node_id": node_id, "name": name, "module": module})
        record = result.single()
        return record.data() if record else {}
