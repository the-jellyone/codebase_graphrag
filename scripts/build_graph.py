"""
Script to parse a repository and build its Knowledge Graph in Neo4j.

Usage:
  python scripts/build_graph.py
  python scripts/build_graph.py --repo test_repo --no-embed
"""

import sys
import argparse
from pathlib import Path

# Ensure project root is in Python path when executed directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from loguru import logger

from ingestion.pipeline import run_ingestion
from graph.connection import Neo4jConnection

from graph.schema import clear_database
from graph.loader import load_parsed_repo_into_graph

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Build Knowledge Graph in Neo4j from a codebase.")
    parser.add_argument(
        "--repo",
        type=str,
        default="test_repo",
        help="Path or GitHub URL of the repository to parse (default: test_repo)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        default=True,
        help="Clear existing graph data before loading (default: True)",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        default=False,
        help="Generate vector embeddings using local Ollama (default: False)",
    )
    args = parser.parse_args()

    console.rule("[bold cyan]Codebase Knowledge Graph Builder[/bold cyan]")
    logger.info(f"Target Repository: {args.repo}")

    # 1. Parse repository into AST nodes and edges (saved to data/parsed.json)
    logger.info("Step 1: Running AST Ingestion Pipeline...")
    parse_result = run_ingestion(args.repo)


    # 2. Connect to Neo4j
    logger.info("Step 2: Connecting to Neo4j...")
    conn = Neo4jConnection()
    driver = conn.get_driver()

    if args.clear:
        logger.info("Clearing previous graph state in Neo4j...")
        clear_database(driver)

    # 3. Ingest into Neo4j
    logger.info("Step 3: Ingesting nodes and relationships into Neo4j...")
    load_parsed_repo_into_graph(
        parse_result,
        driver=driver,
        generate_embeddings=args.embed,
    )

    # 4. Query Database Summary
    logger.info("Step 4: Verifying database contents...")
    _print_graph_summary(conn)

    console.rule("[bold green]Knowledge Graph Build Complete![/bold green]")
    console.print(
        "\n👉 [bold yellow]Open your browser at:[/bold yellow] [bold link=http://localhost:7474]http://localhost:7474[/bold link]\n"
        "   [dim]Try this Cypher query:[/dim] [cyan]MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50[/cyan]\n"
    )

    conn.close()


def _print_graph_summary(conn: Neo4jConnection) -> None:
    """Query Neo4j and display a Rich summary table of labels and relationships."""
    # Count nodes by label
    node_query = """
    MATCH (n)
    RETURN labels(n)[0] AS label, count(n) AS count
    ORDER BY count DESC
    """
    node_records = conn.run_query(node_query)

    # Count edges by type
    edge_query = """
    MATCH ()-[r]->()
    RETURN type(r) AS rel_type, count(r) AS count
    ORDER BY count DESC
    """
    edge_records = conn.run_query(edge_query)

    # Render Node Table
    node_table = Table(title="Knowledge Graph Nodes in Neo4j", show_header=True, header_style="bold magenta")
    node_table.add_column("Node Label", style="cyan")
    node_table.add_column("Total Count", justify="right", style="green")
    for r in node_records:
        node_table.add_row(r["label"] or "Unknown", str(r["count"]))

    # Render Edge Table
    edge_table = Table(title="Knowledge Graph Relationships in Neo4j", show_header=True, header_style="bold magenta")
    edge_table.add_column("Relationship Type", style="cyan")
    edge_table.add_column("Total Count", justify="right", style="green")
    for r in edge_records:
        edge_table.add_row(r["rel_type"] or "Unknown", str(r["count"]))

    console.print()
    console.print(node_table)
    console.print()
    console.print(edge_table)


if __name__ == "__main__":
    main()
