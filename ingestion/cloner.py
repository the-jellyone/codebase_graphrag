"""
Repo cloner and local path resolver.

Handles two entry points:
  1. A GitHub URL  →  clones the repo into data/repos/<name>/
  2. A local path  →  validates it exists and returns it as-is

The rest of the pipeline only ever sees a local filesystem path.
"""

from __future__ import annotations
import os
import shutil
from pathlib import Path
from loguru import logger
from git import Repo, GitCommandError


# Where remote repos will be stored locally
REPOS_DIR = Path("data/repos")


def resolve_repo(source: str, force_reclone: bool = False) -> Path:
    """
    Resolve `source` to an absolute local path.

    Args:
        source:        GitHub URL (https/git) or an absolute/relative local path.
        force_reclone: If True and source is a URL, delete and re-clone even if
                       the repo already exists locally.

    Returns:
        Absolute Path to the repo root directory.

    Raises:
        FileNotFoundError: If a local path is given but doesn't exist.
        GitCommandError:   If cloning fails.
    """
    if _is_url(source):
        return _clone(source, force_reclone)
    else:
        return _validate_local(source)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_url(source: str) -> bool:
    """Return True if source looks like a git remote URL."""
    return source.startswith(("https://", "http://", "git@"))


def _clone(url: str, force: bool) -> Path:
    """Clone a remote repo and return its local path."""
    repo_name = _repo_name_from_url(url)
    dest = REPOS_DIR / repo_name

    if dest.exists():
        if force:
            logger.info(f"Force re-clone: removing existing {dest}")
            shutil.rmtree(dest)
        else:
            logger.info(f"Repo already cloned at {dest}, skipping clone.")
            return dest.resolve()

    REPOS_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(f"Cloning {url} → {dest}")
    try:
        Repo.clone_from(url, str(dest))
        logger.success(f"Clone complete: {dest}")
        return dest.resolve()
    except GitCommandError as exc:
        logger.error(f"Git clone failed: {exc}")
        raise


def _validate_local(path_str: str) -> Path:
    """Validate and return an absolute path to a local repo."""
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Local path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")
    logger.info(f"Using local repo at {path}")
    return path


def _repo_name_from_url(url: str) -> str:
    """Extract 'owner_reponame' from a GitHub URL for use as the local dir name."""
    # e.g. https://github.com/the-jellyone/codebase_graphrag.git
    #   → "the-jellyone_codebase_graphrag"
    clean = url.rstrip("/").rstrip(".git")
    parts = clean.split("/")
    # Take the last two segments: owner + repo name
    return "_".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
