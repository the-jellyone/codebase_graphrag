"""
Ingestion pipeline orchestrator.

Runs in order:
  1. Resolve the source (URL or local path) via cloner.resolve_repo
  2. Parse all Python files via parser.parse_repo
  3. Serialise the ParseResult to data/parsed.json (+ optional pretty log)

Usage:
  from ingestion.pipeline import run_ingestion
  result = run_ingestion("https://github.com/owner/repo")
  # or
  result = run_ingestion("/abs/path/to/local/repo")
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from ingestion.cloner import resolve_repo
from ingestion.parser import parse_repo
from ingestion.models import ParseResult


OUTPUT_DIR  = Path("data")
OUTPUT_FILE = OUTPUT_DIR / "parsed.json"


def run_ingestion(source: str, force_reclone: bool = False) -> ParseResult:
    """
    Full ingestion pipeline: resolve → parse → persist.

    Args:
        source:        GitHub URL or local path to the repo.
        force_reclone: Re-clone even if the repo already exists locally.

    Returns:
        ParseResult containing all extracted nodes and edges.
    """
    logger.info("=" * 60)
    logger.info(f"Starting ingestion for: {source}")
    logger.info("=" * 60)

    # Step 1 — Resolve to a local path
    repo_path = resolve_repo(source, force_reclone=force_reclone)
    logger.info(f"Repo resolved to: {repo_path}")

    # Step 2 — Parse Python files
    result = parse_repo(repo_path)

    # Step 3 — Persist ParseResult as JSON
    _save_result(result)

    _log_summary(result)
    return result


def _save_result(result: ParseResult) -> None:
    """Write the ParseResult to data/parsed.json."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(), f, indent=2, default=str)
    logger.info(f"Saved parse result → {OUTPUT_FILE}")


def load_result() -> ParseResult:
    """Load a previously saved ParseResult from data/parsed.json."""
    if not OUTPUT_FILE.exists():
        raise FileNotFoundError(
            f"No parsed.json found at {OUTPUT_FILE}. Run ingestion first."
        )
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ParseResult(**data)


def _log_summary(result: ParseResult) -> None:
    """Print a breakdown of parsed entities to the logger."""
    from ingestion.models import NodeType

    logger.info("─" * 60)
    logger.info("Parse Summary")
    logger.info("─" * 60)
    logger.info(f"  Total Nodes  : {result.node_count()}")
    for nt in NodeType:
        count = len(result.nodes_by_type(nt))
        if count:
            logger.info(f"    {nt.value:<12} : {count}")
    logger.info(f"  Total Edges  : {result.edge_count()}")
    from ingestion.models import EdgeType
    edge_counts: dict[str, int] = {}
    for e in result.edges:
        edge_counts[e.type] = edge_counts.get(e.type, 0) + 1
    for etype, count in sorted(edge_counts.items()):
        logger.info(f"    {etype:<12} : {count}")
    logger.info("─" * 60)
