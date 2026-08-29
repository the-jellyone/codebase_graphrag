"""
Tool: graph_rag_search

Semantic + structural retrieval via the existing hybrid RAG pipeline.
Use for open-ended "understand / explain" questions where you need
code context + graph relationships together.
"""

from graph.connection import get_driver
from retrieval.retriever import retrieve_subgraph_context
from config import OLLAMA_EMBED_MODEL


def graph_rag_search(args: dict) -> dict:
    """
    Perform hybrid graph RAG retrieval, scoped to the current repo.

    Args:
        args:
            query (str): Natural language question or keyword phrase.
            repo_id (str, optional): Repo scope for graph queries.

    Returns:
        dict with keys:
            context (str): Markdown-formatted context from graph traversal.
            seed_nodes (list): Node IDs used as retrieval seeds.
            metrics (dict): Timing and retrieval stats.
            error (str | None): Set if retrieval failed.
    """
    query = args.get("query", "")
    repo_id = args.get("repo_id", "")
    if not query:
        return {"error": "query is required", "context": "", "seed_nodes": [], "metrics": {}}

    try:
        driver = get_driver()
        context_str, seed_nodes, metrics = retrieve_subgraph_context(
            query_text=query,
            driver=driver,
            embed_model=OLLAMA_EMBED_MODEL,
            repo_id=repo_id,
        )
        return {
            "context": context_str,
            "seed_nodes": seed_nodes,
            "metrics": metrics,
            "error": None,
        }
    except Exception as e:
        return {
            "error": str(e),
            "context": "",
            "seed_nodes": [],
            "metrics": {},
        }
