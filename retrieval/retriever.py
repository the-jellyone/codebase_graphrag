"""
Hybrid GraphRAG Retriever.

Combines Neo4j native vector search (finding seed code nodes) with
multi-hop graph traversals (call chains, inheritance, exceptions, configs)
to assemble comprehensive, high-signal codebase context for the LLM.
"""

from __future__ import annotations
from typing import Any, Optional
from neo4j import Driver, Query
from loguru import logger

from client import get_embedder, get_neo4j


class CodeGraphRetriever:
    """Retrieves relevant codebase subgraphs using vector search + graph expansion."""

    def __init__(self, driver: Driver | None = None, embed_fn: Any | None = None):
        self.driver = driver or get_neo4j()
        self.embed = embed_fn or get_embedder()

    def search_vector_seeds(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        """
        Query Neo4j native vector indexes to find the top-K most semantically
        similar Function and Class nodes for a user query.
        """
        query_vector = self.embed(query)
        if not query_vector:
            return []

        cypher = """
        CALL db.index.vector.queryNodes('function_vector_index', $top_k, $vector)
        YIELD node AS fn, score
        RETURN fn.id AS id,
               labels(fn)[0] AS type,
               fn.name AS name,
               fn.file AS file,
               fn.line AS line,
               fn.docstring AS docstring,
               fn.source_code AS source_code,
               score
        UNION
        CALL db.index.vector.queryNodes('class_vector_index', $top_k, $vector)
        YIELD node AS cls, score
        RETURN cls.id AS id,
               labels(cls)[0] AS type,
               cls.name AS name,
               cls.file AS file,
               cls.line AS line,
               cls.docstring AS docstring,
               cls.source_code AS source_code,
               score
        ORDER BY score DESC
        LIMIT $top_k
        """
        with self.driver.session() as session:
            result = session.run(Query(text=cypher), {"top_k": top_k, "vector": query_vector})
            return [record.data() for record in result]

    def expand_subgraph(self, node_ids: list[str]) -> dict[str, Any]:
        """
        For a given list of seed node IDs, traverse 1-hop relationships:
        - Downstream: what does this node CALL, RAISE, READ?
        - Upstream: who CALLS this node?
        - Hierarchy: what does this node INHERIT or CONTAIN?
        """
        if not node_ids:
            return {"calls": [], "called_by": [], "raises": [], "reads": [], "inherits": []}

        cypher = """
        UNWIND $node_ids AS seed_id
        MATCH (seed {id: seed_id})

        // Outbound calls
        OPTIONAL MATCH (seed)-[:CALLS]->(callee)
        // Inbound callers
        OPTIONAL MATCH (caller)-[:CALLS]->(seed)
        // Exceptions raised
        OPTIONAL MATCH (seed)-[:RAISES]->(exc:Exception)
        // Configs read
        OPTIONAL MATCH (seed)-[:READS]->(cfg:Config)
        // Inheritance
        OPTIONAL MATCH (seed)-[:INHERITS]->(parent:Class)

        RETURN seed.id AS seed_id,
               seed.name AS seed_name,
               collect(DISTINCT {id: callee.id, name: callee.name, file: callee.file, line: callee.line}) AS calls,
               collect(DISTINCT {id: caller.id, name: caller.name, file: caller.file, line: caller.line}) AS called_by,
               collect(DISTINCT {name: exc.name, file: exc.file}) AS raises,
               collect(DISTINCT {name: cfg.name, file: cfg.file}) AS reads,
               collect(DISTINCT {name: parent.name, file: parent.file}) AS inherits
        """
        with self.driver.session() as session:
            result = session.run(Query(text=cypher), {"node_ids": node_ids})
            records = [record.data() for record in result]

        return {"expansions": records}

    def retrieve(self, query: str, top_k: int = 3) -> dict[str, Any]:
        """
        Full hybrid retrieval pipeline:
        1. Find seed nodes via vector similarity
        2. Expand graph relationships around seeds
        3. Assemble formatted prompt context
        """
        seeds = self.search_vector_seeds(query, top_k=top_k)
        seed_ids = [s["id"] for s in seeds]
        subgraph = self.expand_subgraph(seed_ids)
        formatted_context = self.format_context_for_llm(seeds, subgraph)

        return {
            "query": query,
            "seeds": seeds,
            "subgraph": subgraph,
            "context": formatted_context,
        }

    def format_context_for_llm(self, seeds: list[dict[str, Any]], subgraph: dict[str, Any]) -> str:
        """Format the retrieved graph and source code into a compact, token-efficient context."""
        if not seeds:
            return "No relevant codebase entities found."

        # Map expansions by seed ID for quick lookup
        exp_map = {e["seed_id"]: e for e in subgraph.get("expansions", [])}

        blocks: list[str] = ["[CODEBASE CONTEXT]"]

        for seed in seeds:
            sid = seed["id"]
            stype = seed["type"]
            sname = seed["name"]
            sfile = seed["file"]
            sline = seed.get("line") or 1
            source = (seed.get("source_code") or "").strip()
            doc = (seed.get("docstring") or "").strip()

            lang = "typescript" if sfile.endswith((".ts", ".tsx")) else "python"

            header = f'<code_entity type="{stype}" name="{sname}" file="{sfile}:{sline}">'
            lines = [header]

            if doc:
                lines.append(f"docstring: {doc}")

            # Append graph relationships inline
            if sid in exp_map:
                exp = exp_map[sid]
                calls = [c["name"] for c in exp.get("calls", []) if c.get("name")]
                callers = [c["name"] for c in exp.get("called_by", []) if c.get("name")]
                raises = [e["name"] for e in exp.get("raises", []) if e.get("name")]
                reads = [r["name"] for r in exp.get("reads", []) if r.get("name")]
                inherits = [i["name"] for i in exp.get("inherits", []) if i.get("name")]

                if calls:
                    lines.append(f"calls: {', '.join(calls)}")
                if callers:
                    lines.append(f"called_by: {', '.join(callers)}")
                if raises:
                    lines.append(f"raises: {', '.join(raises)}")
                if reads:
                    lines.append(f"reads_config: {', '.join(reads)}")
                if inherits:
                    lines.append(f"inherits: {', '.join(inherits)}")

            if source:
                lines.append(f"```{lang}\n{source}\n```")

            lines.append("</code_entity>")
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

