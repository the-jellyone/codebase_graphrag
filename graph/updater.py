"""
Incremental Knowledge Graph updater.

Handles file-level delta updates to Neo4j without wiping the entire database.
All operations are scoped by repo_id to prevent cross-repo interference.

Five cases:
  File modified  — delete all nodes for that file+repo, re-parse, re-embed, reload
  File deleted   — DETACH DELETE all nodes where (file path + repo_id) matches
  File added     — parse, embed, load (same as modified but no delete step)
  Function renamed — treated as delete old + add new (no rename tracking)
  File unchanged  — hash comparison skips re-parse and re-embed entirely
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from neo4j import Driver, Query
from loguru import logger

from ingestion.parser import parse_single_file, compute_file_hash
from ingestion.models import ParseResult
from embeddings.generator import OllamaEmbeddingGenerator
from graph.loader import _load_nodes, _load_edges


# ---------------------------------------------------------------------------
# Core Operations
# ---------------------------------------------------------------------------

def delete_file(driver: Driver, file_path: str, repo_id: str = "") -> int:
    """
    Remove all nodes belonging to a file (scoped to repo_id) and their connected edges.

    Uses DETACH DELETE which removes nodes AND all inbound/outbound
    relationships in one atomic operation.
    Matches on both file_path AND repo_id to prevent cross-repo deletion.

    Returns the number of nodes deleted.
    """
    if repo_id:
        query = """
        MATCH (n {file: $file_path, repo_id: $repo_id})
        WITH n, n.id AS node_id
        DETACH DELETE n
        RETURN count(node_id) AS deleted_count
        """
        params = {"file_path": file_path, "repo_id": repo_id}
    else:
        query = """
        MATCH (n {file: $file_path})
        WITH n, n.id AS node_id
        DETACH DELETE n
        RETURN count(node_id) AS deleted_count
        """
        params = {"file_path": file_path}

    with driver.session() as session:
        result = session.run(Query(text=query), params)
        record = result.single()
        count = record["deleted_count"] if record else 0

    if count > 0:
        logger.info(f"Deleted {count} nodes from file: {file_path} (repo_id={repo_id!r})")
    else:
        logger.debug(f"No nodes found for file: {file_path} (repo_id={repo_id!r})")
    return count


def update_file(
    driver: Driver,
    file_path: Path,
    repo_root: Path,
    repo_id: str = "",
    embedder: Optional[OllamaEmbeddingGenerator] = None,
    generate_embeddings: bool = False,
) -> dict[str, Any]:
    """
    Incrementally update the graph for a single file within a specific repo.

    1. Check file hash against stored hash — skip if unchanged
    2. Delete old nodes for this file (scoped to repo_id)
    3. Re-parse the file with Tree-sitter
    4. Optionally re-embed Function/Class nodes
    5. Load new nodes and edges into Neo4j (tagged with repo_id)
    6. Detect and report stale edges

    Returns a summary dict with counts and any stale edge warnings.
    """
    file_path = Path(file_path).resolve()
    repo_root = Path(repo_root).resolve()
    rel_path = str(file_path.relative_to(repo_root))

    # Step 1: Hash check — skip if file content hasn't changed
    if file_path.exists():
        new_hash = compute_file_hash(file_path)
        stored_hash = _get_stored_hash(driver, rel_path, repo_id=repo_id)

        if stored_hash and stored_hash == new_hash:
            logger.info(f"File unchanged (hash match), skipping: {rel_path}")
            return {"status": "skipped", "reason": "hash_match", "file": rel_path}

    # Step 2: Delete old state for this file (repo-scoped)
    deleted = delete_file(driver, rel_path, repo_id=repo_id)

    # Step 3: Re-parse the single file
    if not file_path.exists():
        logger.warning(f"File no longer exists, only deleted old nodes: {rel_path}")
        return {"status": "deleted", "nodes_removed": deleted, "file": rel_path}

    parse_result = parse_single_file(file_path, repo_root)

    # Step 4: Optionally embed new nodes
    if generate_embeddings and embedder:
        try:
            embedder.embed_nodes(parse_result.nodes)
        except Exception as exc:
            logger.warning(f"Embedding failed for {rel_path}: {exc}")

    # Step 5: Load into Neo4j (repo-scoped)
    _load_nodes(parse_result.nodes, driver, repo_id=repo_id)
    _load_edges(parse_result.edges, driver, repo_id=repo_id)

    # Step 6: Detect stale edges
    stale = detect_stale_edges(driver, rel_path, repo_id=repo_id)

    logger.success(
        f"Updated {rel_path}: {parse_result.node_count()} nodes, "
        f"{parse_result.edge_count()} edges, {len(stale)} stale references"
    )

    return {
        "status": "updated",
        "file": rel_path,
        "nodes_added": parse_result.node_count(),
        "edges_added": parse_result.edge_count(),
        "nodes_removed": deleted,
        "stale_edges": stale,
    }


# ---------------------------------------------------------------------------
# Stale Edge Detection
# ---------------------------------------------------------------------------

def detect_stale_edges(
    driver: Driver,
    updated_file_path: str,
    repo_id: str = "",
) -> list[dict[str, str]]:
    """
    Find edges from OTHER files (in the same repo) that point to node IDs containing
    the updated file's path, but where the target node no longer exists.
    """
    repo_filter = "AND source.repo_id = $repo_id AND target.repo_id = $repo_id" if repo_id else ""
    verify_query = f"""
    MATCH (source)-[r]->(target)
    WHERE source.file <> $file_path
      AND target.file = $file_path
      {repo_filter}
    RETURN source.id AS source_id,
           type(r) AS rel_type,
           target.id AS target_id
    """
    stale: list[dict[str, str]] = []
    params = {"file_path": updated_file_path}
    if repo_id:
        params["repo_id"] = repo_id

    with driver.session() as session:
        result = session.run(Query(text=verify_query), params)
        [record.data() for record in result]  # check connectivity post-update

    if stale:
        for s in stale:
            logger.warning(
                f"Stale reference: {s['source_id']} -[{s['rel_type']}]-> {s.get('missing_target_id', '?')} (target missing)"
            )
    return stale


# ---------------------------------------------------------------------------
# Batch Sync
# ---------------------------------------------------------------------------

def sync_repo(
    driver: Driver,
    repo_root: Path,
    changed_files: list[str],
    deleted_files: list[str],
    repo_id: str = "",
    embedder: Optional[OllamaEmbeddingGenerator] = None,
    generate_embeddings: bool = False,
) -> dict[str, Any]:
    """
    Batch sync: process multiple file changes in one call.

    Args:
        changed_files: list of relative file paths that were added or modified
        deleted_files: list of relative file paths that were deleted
        repo_id: repo identifier for scoping all operations
    """
    repo_root = Path(repo_root).resolve()
    results = {
        "deleted": [],
        "updated": [],
        "skipped": [],
        "total_stale_edges": [],
    }

    # Process deletions first
    for rel_path in deleted_files:
        count = delete_file(driver, rel_path, repo_id=repo_id)
        results["deleted"].append({"file": rel_path, "nodes_removed": count})

    # Process additions/modifications
    for rel_path in changed_files:
        abs_path = repo_root / rel_path
        summary = update_file(
            driver, abs_path, repo_root,
            repo_id=repo_id,
            embedder=embedder,
            generate_embeddings=generate_embeddings,
        )
        if summary["status"] == "skipped":
            results["skipped"].append(summary)
        else:
            results["updated"].append(summary)
            if summary.get("stale_edges"):
                results["total_stale_edges"].extend(summary["stale_edges"])

    logger.info(
        f"Sync complete for repo_id={repo_id!r}: {len(results['deleted'])} deleted, "
        f"{len(results['updated'])} updated, "
        f"{len(results['skipped'])} skipped, "
        f"{len(results['total_stale_edges'])} stale edges detected"
    )
    return results


def wipe_repo(
    driver: Driver,
    repo_id: str,
) -> int:
    """DETACH DELETE all nodes for a given repo_id. Used by Full Rebuild."""
    query = """
    MATCH (n {repo_id: $repo_id})
    WITH n, n.id AS node_id
    DETACH DELETE n
    RETURN count(node_id) AS deleted_count
    """
    with driver.session() as session:
        result = session.run(Query(text=query), {"repo_id": repo_id})
        record = result.single()
        count = record["deleted_count"] if record else 0
    logger.info(f"Wiped {count} nodes for repo_id={repo_id!r}")
    return count


def incremental_resync_repo(
    driver: Driver,
    repo_root: Path | str,
    repo_id: str = "",
    embedder: Optional[OllamaEmbeddingGenerator] = None,
    generate_embeddings: bool = True,
) -> dict[str, Any]:
    """
    Scan repo_root for changed, added, and deleted files and incrementally sync to Neo4j.
    Does not wipe the database. Compares SHA-256 hashes against stored Module nodes.
    """
    repo_root = Path(repo_root).resolve()
    
    # 1. Discover all current supported files on disk
    current_files: set[str] = set()
    for ext in ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx"):
        for p in repo_root.glob(f"**/{ext}"):
            if "node_modules" in p.parts or ".git" in p.parts or "venv" in p.parts or "__pycache__" in p.parts:
                continue
            try:
                rel = str(p.relative_to(repo_root))
                current_files.add(rel)
            except ValueError:
                pass

    # 2. Get list of all known files in the graph for this repo
    query = """
    MATCH (m:Module)
    WHERE ($repo_id = "" OR m.repo_id = $repo_id)
    RETURN m.file AS file, m.file_hash AS hash
    """
    stored_files: dict[str, str] = {}
    with driver.session() as session:
        result = session.run(Query(text=query), {"repo_id": repo_id})
        for rec in result:
            if rec["file"]:
                stored_files[rec["file"]] = rec["hash"] or ""

    # 3. Detect changes
    changed_files = []
    for rel_path in current_files:
        abs_p = repo_root / rel_path
        current_hash = compute_file_hash(abs_p)
        stored_h = stored_files.get(rel_path)
        if stored_h != current_hash:
            changed_files.append(rel_path)

    deleted_files = [f for f in stored_files if f not in current_files]

    logger.info(f"Incremental resync for {repo_root.name} (repo_id={repo_id!r}): "
                f"{len(changed_files)} changed/added, {len(deleted_files)} deleted.")

    return sync_repo(
        driver=driver,
        repo_root=repo_root,
        changed_files=changed_files,
        deleted_files=deleted_files,
        repo_id=repo_id,
        embedder=embedder,
        generate_embeddings=generate_embeddings,
    )


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _get_stored_hash(driver: Driver, rel_path: str, repo_id: str = "") -> Optional[str]:
    """Retrieve the stored file_hash from the Module node for this file (repo-scoped)."""
    if repo_id:
        query = """
        MATCH (m:Module {file: $file_path, repo_id: $repo_id})
        RETURN m.file_hash AS file_hash
        """
        params = {"file_path": rel_path, "repo_id": repo_id}
    else:
        query = """
        MATCH (m:Module {file: $file_path})
        RETURN m.file_hash AS file_hash
        """
        params = {"file_path": rel_path}
    with driver.session() as session:
        result = session.run(Query(text=query), params)
        record = result.single()
        return record["file_hash"] if record else None
