"""
Tool: get_file_content

Reads raw source code from a file in the indexed repository.
Use when the model needs the full implementation, not just AST nodes.
"""

from pathlib import Path


# Base repo path — resolved relative to project root at runtime
_REPO_ROOT: Path | None = None


def _resolve_repo_root() -> Path:
    """Find the repo root by walking up from this file."""
    global _REPO_ROOT
    if _REPO_ROOT is None:
        # project root is two levels up from agent/tools/
        _REPO_ROOT = Path(__file__).parent.parent.parent
    return _REPO_ROOT


def get_file_content(args: dict) -> dict:
    """
    Read raw source code for a given file path.

    Args:
        args:
            file_path (str): Relative path from repo root (e.g. "backend/services/user_service.py")
                             OR an absolute path.

    Returns:
        dict with keys:
            content (str): Full file source code.
            file_path (str): Resolved path that was read.
            lines (int): Total line count.
            error (str | None): Set if file not found or unreadable.
    """
    file_path = args.get("file_path", "")
    if not file_path:
        return {"error": "file_path is required", "content": "", "file_path": "", "lines": 0}

    path = Path(file_path)
    if not path.is_absolute():
        path = _resolve_repo_root() / file_path

    if not path.exists():
        return {
            "error": f"File not found: {file_path}",
            "content": "",
            "file_path": str(path),
            "lines": 0,
        }

    try:
        content = path.read_text(encoding="utf-8")
        return {
            "content": content,
            "file_path": str(path),
            "lines": len(content.splitlines()),
            "error": None,
        }
    except Exception as e:
        return {
            "error": str(e),
            "content": "",
            "file_path": str(path),
            "lines": 0,
        }
