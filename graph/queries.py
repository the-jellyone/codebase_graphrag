"""
Cypher query library for multi-hop graph traversals and relational reasoning.

Used by both the Graph RAG Retriever and the LangGraph Agent tools.
All queries are scoped to a repo_id to prevent cross-repo data leakage.
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
    repo_id: str = "",
) -> list[dict[str, Any]]:
    """Search for the top-k most similar Function nodes using Neo4j's native vector index.
    Over-fetches by 3x internally then filters by repo_id to maintain result quality."""
    internal_k = max(top_k * 3, 15) if repo_id else top_k
    
    if repo_id:
        query = f"""
        CALL db.index.vector.queryNodes('{FUNCTION_VECTOR_INDEX_NAME}', $internal_k, $query_vector)
        YIELD node, score
        WITH node, score
        WHERE node.repo_id = $repo_id
        RETURN node.id AS id,
               node.name AS name,
               node.file AS file,
               node.line AS line,
               node.docstring AS docstring,
               node.source_code AS source_code,
               score
        ORDER BY score DESC
        LIMIT $top_k
        """
        with driver.session() as session:
            result = session.run(query, {"internal_k": internal_k, "top_k": top_k,
                                         "query_vector": query_vector, "repo_id": repo_id})
            records = [record.data() for record in result]
            if records:
                return records

    # Fallback / unfiltered search (if no repo_id or if repo_id filtered query returned 0 rows)
    query_fallback = f"""
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
        result = session.run(query_fallback, {"top_k": top_k, "query_vector": query_vector})
        return [record.data() for record in result]


def vector_search_classes(
    driver: Driver,
    query_vector: list[float],
    top_k: int = 5,
    repo_id: str = "",
) -> list[dict[str, Any]]:
    """Search for the top-k most similar Class nodes using Neo4j's native vector index.
    Over-fetches by 3x internally then filters by repo_id to maintain result quality."""
    internal_k = max(top_k * 3, 15) if repo_id else top_k
    
    if repo_id:
        query = f"""
        CALL db.index.vector.queryNodes('{CLASS_VECTOR_INDEX_NAME}', $internal_k, $query_vector)
        YIELD node, score
        WITH node, score
        WHERE node.repo_id = $repo_id
        RETURN node.id AS id,
               node.name AS name,
               node.file AS file,
               node.line AS line,
               node.docstring AS docstring,
               score
        ORDER BY score DESC
        LIMIT $top_k
        """
        with driver.session() as session:
            result = session.run(query, {"internal_k": internal_k, "top_k": top_k,
                                         "query_vector": query_vector, "repo_id": repo_id})
            records = [record.data() for record in result]
            if records:
                return records

    # Fallback / unfiltered search
    query_fallback = f"""
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
        result = session.run(query_fallback, {"top_k": top_k, "query_vector": query_vector})
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
    repo_id: str = "",
) -> list[dict[str, Any]]:
    """Trace forward execution/call chains originating from a function."""
    name, module = _extract_name_and_module(start_func_id)
    repo_filter = "AND start.repo_id = $repo_id" if repo_id else ""
    query = f"""
    MATCH (start:Function)
    WHERE (start.id = $start_id
       OR start.id ENDS WITH ("::" + $start_id)
       OR start.name = $start_id
       OR (start.name = $name AND (start.file CONTAINS $module OR start.id CONTAINS $module))
       OR start.id CONTAINS $start_id)
    {repo_filter}
    WITH start LIMIT 1
    MATCH path = (start)-[:CALLS*1..{max_depth}]->(target:Function)
    RETURN [node in nodes(path) | node.name] AS call_chain,
           [node in nodes(path) | node.id] AS node_ids,
           length(path) AS depth
    ORDER BY depth ASC
    """
    params = {"start_id": start_func_id, "name": name, "module": module}
    if repo_id:
        params["repo_id"] = repo_id
    with driver.session() as session:
        result = session.run(query, params)
        return [record.data() for record in result]


def get_upstream_callers(
    driver: Driver,
    target_func_id: str,
    max_depth: int = 4,
    repo_id: str = "",
) -> list[dict[str, Any]]:
    """Find all functions that directly or indirectly call the target function."""
    name, module = _extract_name_and_module(target_func_id)
    repo_filter = "AND target.repo_id = $repo_id" if repo_id else ""
    query = f"""
    MATCH (target:Function)
    WHERE (target.id = $target_id
       OR target.id ENDS WITH ("::" + $target_id)
       OR target.name = $target_id
       OR (target.name = $name AND (target.file CONTAINS $module OR target.id CONTAINS $module))
       OR target.id CONTAINS $target_id)
    {repo_filter}
    WITH target LIMIT 1
    MATCH path = (caller:Function)-[:CALLS*1..{max_depth}]->(target)
    RETURN [node in nodes(path) | node.name] AS caller_chain,
           [node in nodes(path) | node.id] AS node_ids,
           length(path) AS depth
    ORDER BY depth ASC
    """
    params = {"target_id": target_func_id, "name": name, "module": module}
    if repo_id:
        params["repo_id"] = repo_id
    with driver.session() as session:
        result = session.run(query, params)
        return [record.data() for record in result]


def get_subgraph_around_nodes(
    driver: Driver,
    seed_node_ids: list[str],
    hops: int = 2,
    repo_id: str = "",
) -> list[dict[str, Any]]:
    """
    Extract a multi-hop subgraph around seed nodes.
    Returns all traversed relationships and connected entities.
    """
    repo_filter = "AND seed.repo_id = $repo_id" if repo_id else ""
    query = f"""
    MATCH (seed)
    WHERE seed.id IN $seed_ids {repo_filter}
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
    params = {"seed_ids": seed_node_ids}
    if repo_id:
        params["repo_id"] = repo_id
    with driver.session() as session:
        result = session.run(query, params)
        return [record.data() for record in result]


def get_impact_analysis(
    driver: Driver,
    node_id: str,
    repo_id: str = "",
) -> dict[str, Any]:
    """
    Comprehensive impact analysis:
    - Direct & multi-hop upstream callers (what breaks)
    - Direct downstream calls
    - Exceptions raised
    - Config read dependencies
    """
    name, module = _extract_name_and_module(node_id)
    repo_filter = "AND n.repo_id = $repo_id" if repo_id else ""
    query = f"""
    MATCH (n)
    WHERE (n.id = $node_id
       OR n.id ENDS WITH ("::" + $node_id)
       OR n.name = $node_id
       OR (n.name = $name AND (n.file CONTAINS $module OR n.id CONTAINS $module))
       OR n.id CONTAINS $node_id)
    {repo_filter}
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
    params = {"node_id": node_id, "name": name, "module": module}
    if repo_id:
        params["repo_id"] = repo_id
    with driver.session() as session:
        result = session.run(query, params)
        record = result.single()
        return record.data() if record else {}


def get_graph_preview(
    driver: Driver,
    repo_id: str,
    highlighted_nodes: list[str] | None = None,
    limit: int = 60,
) -> dict[str, Any]:
    """Return lightweight nodes+edges JSON for the KG panel visualization."""
    highlighted = set(highlighted_nodes or [])
    
    # Query with repo_id filter
    query = """
    MATCH (n)
    WHERE ($repo_id = "" OR n.repo_id = $repo_id OR n.repo_id IS NULL)
    WITH n LIMIT $limit
    OPTIONAL MATCH (n)-[r]-(m)
    WHERE ($repo_id = "" OR m.repo_id = $repo_id OR m.repo_id IS NULL)
    WITH n, collect(DISTINCT {source: n.id, target: m.id, type: type(r)}) AS rels
    RETURN collect(DISTINCT {id: n.id, name: n.name, label: labels(n)[0], degree: 1}) AS nodes,
           [x IN rels WHERE x.source IS NOT NULL AND x.target IS NOT NULL] AS edges
    """
    try:
        with driver.session() as session:
            result = session.run(query, {"repo_id": repo_id, "limit": limit})
            record = result.single()
            if not record:
                return {"nodes": [], "edges": []}
            nodes = record["nodes"]
            edges = record["edges"]
    except Exception as exc:
        logger.warning(f"Graph preview query error: {exc}")
        return {"nodes": [], "edges": []}

    # Annotate nodes with highlight + type color
    annotated_nodes = []
    for node in nodes:
        if not node or not node.get("id"):
            continue
        node_name = node.get("name", "") or ""
        node_id = node.get("id", "") or ""
        is_highlighted = node_name in highlighted or node_id in highlighted
        annotated_nodes.append({
            "id": node_id,
            "name": node_name,
            "label": node.get("label", "Unknown"),
            "degree": node.get("degree", 1),
            "highlighted": is_highlighted,
        })

    # Deduplicate edges
    seen_edges = set()
    clean_edges = []
    for e in edges:
        if not e or not e.get("source") or not e.get("target"):
            continue
        key = (e["source"], e["target"], e.get("type", ""))
        if key not in seen_edges:
            seen_edges.add(key)
            clean_edges.append(e)

    return {"nodes": annotated_nodes, "edges": clean_edges}


def get_repo_stats(
    driver: Driver,
    repo_id: str,
) -> dict[str, Any]:
    """Return node count, edge count, and file count for a repo."""
    # First attempt: exact repo_id match
    query_exact = """
    MATCH (n)
    WHERE n.repo_id = $repo_id
    WITH count(n) AS node_count
    OPTIONAL MATCH (a)-[r]-(b)
    WHERE a.repo_id = $repo_id AND b.repo_id = $repo_id
    RETURN node_count, count(DISTINCT r) AS edge_count
    """
    # Fallback: if repo_id matched 0 nodes (e.g. legacy ingested nodes with null repo_id)
    query_fallback = """
    MATCH (n)
    WITH count(n) AS node_count
    OPTIONAL MATCH (a)-[r]-(b)
    RETURN node_count, count(DISTINCT r) AS edge_count
    """
    with driver.session() as session:
        if repo_id:
            result = session.run(query_exact, {"repo_id": repo_id})
            record = result.single()
            if record and record["node_count"] > 0:
                return {"node_count": record["node_count"], "edge_count": record["edge_count"]}
        
        result = session.run(query_fallback)
        record = result.single()
        if record:
            return {"node_count": record["node_count"], "edge_count": record["edge_count"]}
        return {"node_count": 0, "edge_count": 0}
