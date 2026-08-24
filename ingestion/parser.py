"""
Tree-sitter based parser for Python and TypeScript source files.

Why tree-sitter instead of Python's `ast` module?
  - Language-agnostic: same API for Python and TypeScript (and any other
    language we add later by dropping in a new grammar)
  - Fault-tolerant: tree-sitter parses partial/broken files and still
    produces a usable tree; `ast.parse()` raises SyntaxError and gives up
  - Faster for large repos: tree-sitter is a C library, incremental parsing
    is possible in future iterations
  - Uniform query language: S-expression tree-sitter queries make extraction
    patterns explicit and testable independent of Python logic

Extraction strategy per language
---------------------------------
Python (.py)
  Nodes:  function_definition, class_definition  → Function / Class
  Module: one per file (from path)
  Edges:  CALLS  (call expressions + import scope resolution)
          IMPORTS (import_statement, import_from_statement)
          INHERITS (class base_list)
          HAS_METHOD (class → its methods)
          CONTAINS (module → top-level defs)
          RAISES (raise_statement inside function)
          READS  (attribute access on `config` / os.getenv calls)

TypeScript (.ts / .tsx)
  Nodes:  function_declaration, method_definition, interface_declaration → Function / Class
  Module: one per file
  Edges:  CALLS, IMPORTS, DEFINES_TYPE (interface → type node), USES_TYPE
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional


from loguru import logger
import tree_sitter_python as tspython
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser, Node


from ingestion.models import (
    EdgeType,
    NodeType,
    ParsedEdge,
    ParsedNode,
    ParseResult,
)

# ---------------------------------------------------------------------------
# Language setup — load grammars once at module level
# ---------------------------------------------------------------------------

PY_LANGUAGE = Language(tspython.language())
TS_LANGUAGE = Language(tstypescript.language_typescript())

_py_parser = Parser(PY_LANGUAGE)
_ts_parser = Parser(TS_LANGUAGE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_repo(repo_path: Path) -> ParseResult:
    """
    Parse every Python and TypeScript file in `repo_path`.

    Returns a ParseResult with all nodes and edges ready for Neo4j/ChromaDB.
    """
    repo_path = Path(repo_path).resolve()
    result = ParseResult(repo_path=str(repo_path))

    py_files = _collect_files(repo_path, ".py")
    ts_files = _collect_files(repo_path, ".ts") + _collect_files(repo_path, ".tsx")

    logger.info(f"Found {len(py_files)} Python + {len(ts_files)} TypeScript files")

    for filepath in py_files:
        try:
            _parse_python_file(filepath, repo_path, result)
        except Exception as exc:
            logger.warning(f"Skipping {filepath.name}: {exc}")

    for filepath in ts_files:
        try:
            _parse_typescript_file(filepath, repo_path, result)
        except Exception as exc:
            logger.warning(f"Skipping {filepath.name}: {exc}")

    logger.success(
        f"Parse complete → {result.node_count()} nodes, {result.edge_count()} edges"
    )
    return result


def parse_single_file(file_path: Path, repo_root: Path) -> ParseResult:
    """
    Parse a single file and return its nodes and edges.

    Used by the incremental updater to re-parse only changed files
    instead of the entire repository.
    """
    file_path = Path(file_path).resolve()
    repo_root = Path(repo_root).resolve()
    result = ParseResult(repo_path=str(repo_root))

    suffix = file_path.suffix.lower()
    if suffix == ".py":
        _parse_python_file(file_path, repo_root, result)
    elif suffix in (".ts", ".tsx"):
        _parse_typescript_file(file_path, repo_root, result)
    else:
        logger.warning(f"Unsupported file type: {file_path.suffix}")

    return result


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file's content."""
    content = Path(file_path).read_bytes()
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------

_SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "env",
    "node_modules", ".eggs", "build", "dist",
}


def _collect_files(repo_path: Path, ext: str) -> list[Path]:
    files = []
    for root, dirs, fnames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in fnames:
            if fname.endswith(ext):
                files.append(Path(root) / fname)
    return sorted(files)


# ---------------------------------------------------------------------------
# Python file parser
# ---------------------------------------------------------------------------

def _parse_python_file(filepath: Path, repo_root: Path, result: ParseResult) -> None:
    source_bytes = filepath.read_bytes()
    source_text  = source_bytes.decode("utf-8", errors="ignore")
    tree         = _py_parser.parse(source_bytes)
    root         = tree.root_node

    rel_path   = str(filepath.relative_to(repo_root))
    module_id  = _module_id(rel_path)

    # Module node (with file hash for incremental updates)
    result.nodes.append(ParsedNode(
        id=module_id,
        type=NodeType.MODULE,
        name=_module_name(rel_path),
        file=rel_path,
        file_hash=hashlib.sha256(source_bytes).hexdigest(),
    ))

    # Build import map: local alias → rel_path of the imported module
    import_map = _py_build_import_map(root, source_text, rel_path, repo_root)

    # IMPORTS edges
    _py_extract_imports(root, module_id, rel_path, repo_root, result)

    # Classes and functions
    _py_extract_classes(root, module_id, rel_path, import_map, source_text, result)
    _py_extract_top_functions(root, module_id, rel_path, import_map, source_text, result)


# ── Python: import map ────────────────────────────────────────────────────

def _py_build_import_map(
    root: Node, source: str, rel_path: str, repo_root: Path
) -> dict[str, str]:
    """
    Build {local_alias → resolved_rel_path} for all imports in a file.

    Needed for call resolution: when we see `repository.save()` we look up
    `repository` in this map to find which file it came from.
    """
    import_map: dict[str, str] = {}

    for node in _iter_nodes(root, {"import_statement", "import_from_statement"}):
        if node.type == "import_statement":
            for child in node.children:
                if child.type == "aliased_import":
                    orig = _child_text(child, source, "name")
                    alias = _child_text(child, source, "alias")
                    if orig:
                        path = _dotted_to_path(orig, repo_root, rel_path)
                        if path and alias:
                            import_map[alias] = path
                elif child.type == "dotted_name":
                    name = _node_text(child, source)
                    local = name.split(".")[-1]
                    path = _dotted_to_path(name, repo_root, rel_path)
                    if path:
                        import_map[local] = path

        elif node.type == "import_from_statement":
            from_mod = None
            module_name_node = node.child_by_field_name("module_name")
            if module_name_node:
                from_mod = _node_text(module_name_node, source)

            past_import = False
            for child in node.children:
                if child.type == "from" and from_mod is None:
                    continue
                if child.type in ("dotted_name", "relative_import") and not past_import:
                    if from_mod is None:
                        from_mod = _node_text(child, source)
                elif child.type == "import":
                    past_import = True
                elif past_import:
                    if child.type == "aliased_import":
                        imp_name = _child_text(child, source, "name")
                        imp_alias = _child_text(child, source, "alias")
                        if imp_name and imp_alias:
                            full = f"{from_mod}.{imp_name}" if from_mod else imp_name
                            path = _dotted_to_path(full, repo_root, rel_path) or (
                                _dotted_to_path(from_mod, repo_root, rel_path) if from_mod else None
                            )
                            if path:
                                import_map[imp_alias] = path
                    elif child.type in ("dotted_name", "identifier"):
                        imp_name = _node_text(child, source)
                        full = f"{from_mod}.{imp_name}" if from_mod else imp_name
                        path = _dotted_to_path(full, repo_root, rel_path) or (
                            _dotted_to_path(from_mod, repo_root, rel_path) if from_mod else None
                        )
                        if path:
                            import_map[imp_name] = path

    return import_map


# ── Python: IMPORTS edges ─────────────────────────────────────────────────

def _py_extract_imports(
    root: Node, module_id: str, rel_path: str, repo_root: Path, result: ParseResult
) -> None:
    source = _read_source_from_node(root)
    for node in _iter_nodes(root, {"import_statement", "import_from_statement"}):
        if node.type == "import_statement":
            for child in node.children:
                name = None
                if child.type == "aliased_import":
                    name = _child_text(child, source, "name")
                elif child.type == "dotted_name":
                    name = _node_text(child, source)
                if name:
                    path = _dotted_to_path(name.split()[0], repo_root, rel_path)
                    if path:
                        result.edges.append(ParsedEdge(
                            source=module_id,
                            target=_module_id(path),
                            type=EdgeType.IMPORTS,
                        ))

        elif node.type == "import_from_statement":
            from_mod = None
            module_name_node = node.child_by_field_name("module_name")
            if module_name_node:
                from_mod = _node_text(module_name_node, source)

            past_import = False
            imported_paths = set()
            for child in node.children:
                if child.type in ("dotted_name", "relative_import") and not past_import:
                    if from_mod is None:
                        from_mod = _node_text(child, source)
                elif child.type == "import":
                    past_import = True
                elif past_import:
                    name = None
                    if child.type == "aliased_import":
                        name = _child_text(child, source, "name")
                    elif child.type in ("dotted_name", "identifier"):
                        name = _node_text(child, source)
                    if name and from_mod:
                        full = f"{from_mod}.{name}"
                        sub_path = _dotted_to_path(full, repo_root, rel_path)
                        if sub_path:
                            imported_paths.add(sub_path)

            # If specific submodules were imported, create IMPORTS edges to them
            if imported_paths:
                for imp_path in imported_paths:
                    result.edges.append(ParsedEdge(
                        source=module_id,
                        target=_module_id(imp_path),
                        type=EdgeType.IMPORTS,
                    ))
            elif from_mod:
                # Otherwise import the parent module itself (e.g. from backend.db import repository)
                path = _dotted_to_path(from_mod, repo_root, rel_path)
                if path:
                    result.edges.append(ParsedEdge(
                        source=module_id,
                        target=_module_id(path),
                        type=EdgeType.IMPORTS,
                    ))



# ── Python: classes ───────────────────────────────────────────────────────

def _py_extract_classes(
    root: Node, module_id: str, rel_path: str,
    import_map: dict[str, str], source: str, result: ParseResult,
) -> None:
    for node in root.children:
        if node.type == "class_definition":
            _py_handle_class(node, module_id, rel_path, import_map, source, result)


def _py_handle_class(
    node: Node, module_id: str, rel_path: str,
    import_map: dict[str, str], source: str, result: ParseResult,
) -> None:
    class_name = _child_text(node, source, "name")
    if not class_name:
        return

    class_id  = _node_id(rel_path, class_name)
    docstring = _py_docstring(node, source)

    result.nodes.append(ParsedNode(
        id=class_id,
        type=NodeType.CLASS,
        name=class_name,
        file=rel_path,
        line=node.start_point[0] + 1,
        docstring=docstring,
    ))

    result.edges.append(ParsedEdge(source=module_id, target=class_id, type=EdgeType.CONTAINS))

    # INHERITS — parse argument_list (superclasses)
    for child in node.children:
        if child.type == "argument_list":
            for arg in child.children:
                if arg.type in ("identifier", "attribute"):
                    base_name = _node_text(arg, source)
                    resolved  = _resolve_name(base_name, rel_path, import_map)
                    result.edges.append(ParsedEdge(
                        source=class_id, target=resolved, type=EdgeType.INHERITS
                    ))

    # Methods inside the class body
    body = _get_child_by_type(node, "block")
    if body:
        for child in body.children:
            if child.type in ("function_definition", "decorated_definition"):
                func_node = child if child.type == "function_definition" \
                    else _get_child_by_type(child, "function_definition")
                if func_node:
                    _py_handle_function(
                        func_node, class_id, rel_path, import_map,
                        source, result, parent_class=class_id,
                    )


# ── Python: top-level functions ───────────────────────────────────────────

def _py_extract_top_functions(
    root: Node, module_id: str, rel_path: str,
    import_map: dict[str, str], source: str, result: ParseResult,
) -> None:
    for child in root.children:
        if child.type in ("function_definition", "decorated_definition"):
            func_node = child if child.type == "function_definition" \
                else _get_child_by_type(child, "function_definition")
            if func_node:
                _py_handle_function(
                    func_node, module_id, rel_path,
                    import_map, source, result, parent_class=None,
                )


def _py_handle_function(
    node: Node, owner_id: str, rel_path: str,
    import_map: dict[str, str], source: str, result: ParseResult,
    parent_class: Optional[str],
) -> None:
    func_name = _child_text(node, source, "name")
    if not func_name:
        return

    func_id     = _node_id(rel_path, func_name)
    docstring   = _py_docstring(node, source)
    source_code = _node_text(node, source)

    result.nodes.append(ParsedNode(
        id=func_id,
        type=NodeType.FUNCTION,
        name=func_name,
        file=rel_path,
        line=node.start_point[0] + 1,
        docstring=docstring,
        source_code=source_code,
    ))

    result.edges.append(ParsedEdge(source=owner_id, target=func_id, type=EdgeType.CONTAINS))

    if parent_class:
        result.edges.append(ParsedEdge(
            source=parent_class, target=func_id, type=EdgeType.HAS_METHOD
        ))

    # Walk function body for calls, raises, reads
    _py_extract_calls(node, func_id, rel_path, import_map, source, result)
    _py_extract_raises(node, func_id, rel_path, source, result)
    _py_extract_reads(node, func_id, rel_path, source, result)


# ── Python: CALLS ─────────────────────────────────────────────────────────

def _py_extract_calls(
    func_node: Node, func_id: str, rel_path: str,
    import_map: dict[str, str], source: str, result: ParseResult,
) -> None:
    for node in _iter_nodes(func_node, {"call"}):
        callee_id = _py_resolve_call(node, rel_path, import_map, source)
        if callee_id:
            result.edges.append(ParsedEdge(
                source=func_id, target=callee_id, type=EdgeType.CALLS
            ))


def _py_resolve_call(
    call_node: Node, rel_path: str, import_map: dict[str, str], source: str
) -> Optional[str]:
    """
    Resolve a tree-sitter call node to a target node ID.

    Handles:
      foo()              → same-module function or known import
      module.method()    → look up 'module' in import_map
      self.method()      → skip (runtime dispatch)
    """
    func_child = call_node.child_by_field_name("function")
    if not func_child:
        return None

    if func_child.type == "attribute":
        obj  = _node_text(func_child.child_by_field_name("object"), source) if func_child.child_by_field_name("object") else None
        attr = _node_text(func_child.child_by_field_name("attribute"), source) if func_child.child_by_field_name("attribute") else None

        if not obj or obj == "self" or obj == "cls":
            return None

        if obj in import_map and attr:
            return _node_id(import_map[obj], attr)

        return None  # unresolvable — skip, never guess


    elif func_child.type == "identifier":
        name = _node_text(func_child, source)
        if name in import_map:
            return _module_id(import_map[name]) + "::" + name
        # Same-module call
        return _node_id(rel_path, name)

    return None


# ── Python: RAISES ────────────────────────────────────────────────────────

def _py_extract_raises(
    func_node: Node, func_id: str, rel_path: str, source: str, result: ParseResult,
) -> None:
    for node in _iter_nodes(func_node, {"raise_statement"}):
        # raise SomeException(...)  or  raise SomeException
        exc_node = None
        for child in node.children:
            if child.type in ("call", "identifier", "attribute"):
                exc_node = child
                break
        if not exc_node:
            continue

        exc_name = _node_text(exc_node, source)
        # Strip call args: "NotFoundException(...)" → "NotFoundException"
        exc_name = exc_name.split("(")[0].strip()
        if not exc_name:
            continue

        exc_id = f"exception::{exc_name}"
        if not any(n.id == exc_id for n in result.nodes):
            result.nodes.append(ParsedNode(
                id=exc_id, type=NodeType.EXCEPTION,
                name=exc_name, file=rel_path,
            ))

        result.edges.append(ParsedEdge(
            source=func_id, target=exc_id, type=EdgeType.RAISES
        ))


# ── Python: READS (config) ────────────────────────────────────────────────

def _py_extract_reads(
    func_node: Node, func_id: str, rel_path: str, source: str, result: ParseResult,
) -> None:
    """
    Detect two patterns only:
      1. config.SOME_KEY   → attribute access where object is 'config'
      2. os.getenv("KEY")  → call to os.getenv with a string literal arg
    """
    for node in _iter_nodes(func_node, {"attribute"}):
        obj  = node.child_by_field_name("object")
        attr = node.child_by_field_name("attribute")
        if obj and attr and _node_text(obj, source) == "config":
            config_key = f"config.{_node_text(attr, source)}"
            _emit_config_read(config_key, func_id, rel_path, source, result)

    for node in _iter_nodes(func_node, {"call"}):
        func = node.child_by_field_name("function")
        if not func or func.type != "attribute":
            continue
        obj  = func.child_by_field_name("object")
        attr = func.child_by_field_name("attribute")
        if not obj or not attr:
            continue
        if _node_text(obj, source) == "os" and _node_text(attr, source) == "getenv":
            args = node.child_by_field_name("arguments")
            if args:
                for arg in args.children:
                    if arg.type == "string":
                        raw = _node_text(arg, source).strip("'\"")
                        _emit_config_read(f"env.{raw}", func_id, rel_path, source, result)


def _emit_config_read(
    config_key: str, func_id: str, rel_path: str, source: str, result: ParseResult,
) -> None:
    config_id = f"config::{config_key}"
    if not any(n.id == config_id for n in result.nodes):
        result.nodes.append(ParsedNode(
            id=config_id, type=NodeType.CONFIG,
            name=config_key, file=rel_path,
        ))
    result.edges.append(ParsedEdge(
        source=func_id, target=config_id, type=EdgeType.READS
    ))


# ---------------------------------------------------------------------------
# TypeScript file parser
# ---------------------------------------------------------------------------

def _parse_typescript_file(filepath: Path, repo_root: Path, result: ParseResult) -> None:
    source_bytes = filepath.read_bytes()
    source_text  = source_bytes.decode("utf-8", errors="ignore")
    tree         = _ts_parser.parse(source_bytes)
    root         = tree.root_node

    rel_path  = str(filepath.relative_to(repo_root))
    module_id = _module_id(rel_path)

    # Module node (with file hash for incremental updates)
    result.nodes.append(ParsedNode(
        id=module_id,
        type=NodeType.MODULE,
        name=_module_name(rel_path),
        file=rel_path,
        file_hash=hashlib.sha256(source_bytes).hexdigest(),
    ))

    _ts_extract_imports(root, module_id, rel_path, repo_root, source_text, result)
    _ts_extract_interfaces(root, module_id, rel_path, source_text, result)
    _ts_extract_functions(root, module_id, rel_path, source_text, result)


# ── TypeScript: IMPORTS ────────────────────────────────────────────────────

def _ts_extract_imports(
    root: Node, module_id: str, rel_path: str,
    repo_root: Path, source: str, result: ParseResult,
) -> None:
    """
    Handle ES module imports:
      import { foo } from './bar'
      import * as foo from '../baz'
    """
    for node in _iter_nodes(root, {"import_statement"}):
        source_clause = None
        for child in node.children:
            if child.type == "string":
                source_clause = _node_text(child, source).strip("'\"")
        if source_clause and not source_clause.startswith("."):
            continue  # external package, skip

        if source_clause:
            resolved = _ts_resolve_import_path(source_clause, rel_path, repo_root)
            if resolved:
                result.edges.append(ParsedEdge(
                    source=module_id,
                    target=_module_id(resolved),
                    type=EdgeType.IMPORTS,
                ))


def _ts_resolve_import_path(import_str: str, from_rel: str, repo_root: Path) -> Optional[str]:
    """Resolve a relative TS import path to a repo-relative file path."""
    from_dir = (repo_root / from_rel).parent
    candidate = (from_dir / import_str).resolve()
    for ext in ("", ".ts", ".tsx", "/index.ts"):
        p = Path(str(candidate) + ext)
        if p.exists():
            return str(p.relative_to(repo_root))
    return None


# ── TypeScript: interfaces (DEFINES_TYPE) ─────────────────────────────────

def _ts_extract_interfaces(
    root: Node, module_id: str, rel_path: str, source: str, result: ParseResult,
) -> None:
    for node in _iter_nodes(root, {"interface_declaration"}):
        name_node = node.child_by_field_name("name")
        if not name_node:
            continue
        iface_name = _node_text(name_node, source)
        iface_id   = _node_id(rel_path, iface_name)

        result.nodes.append(ParsedNode(
            id=iface_id,
            type=NodeType.CLASS,   # treat interfaces as Class nodes in KG
            name=iface_name,
            file=rel_path,
            line=node.start_point[0] + 1,
            source_code=_node_text(node, source),
        ))

        # DEFINES_TYPE edge: module → interface
        result.edges.append(ParsedEdge(
            source=module_id, target=iface_id, type=EdgeType.CONTAINS
        ))


# ── TypeScript: functions ─────────────────────────────────────────────────

_TS_FUNC_TYPES = {
    "function_declaration",
    "arrow_function",
    "method_definition",
    "lexical_declaration",   # const foo = async (...) => ...
}


def _ts_extract_functions(
    root: Node, module_id: str, rel_path: str, source: str, result: ParseResult,
) -> None:
    """
    Extract top-level functions and exported arrow functions.
    Also emit CALLS edges for call expressions inside function bodies.
    """
    for node in _iter_nodes(root, {"function_declaration", "export_statement"}):
        func_node = node if node.type == "function_declaration" \
            else _get_child_by_type(node, "function_declaration")
        if not func_node:
            continue

        name_node = func_node.child_by_field_name("name")
        if not name_node:
            continue

        func_name = _node_text(name_node, source)
        func_id   = _node_id(rel_path, func_name)

        result.nodes.append(ParsedNode(
            id=func_id,
            type=NodeType.FUNCTION,
            name=func_name,
            file=rel_path,
            line=func_node.start_point[0] + 1,
            source_code=_node_text(func_node, source),
        ))

        result.edges.append(ParsedEdge(
            source=module_id, target=func_id, type=EdgeType.CONTAINS
        ))

        # CALLS inside this function
        _ts_extract_calls(func_node, func_id, source, result)


def _ts_extract_calls(
    func_node: Node, func_id: str, source: str, result: ParseResult,
) -> None:
    """Emit CALLS edges for call_expression nodes inside a TS function."""
    for node in _iter_nodes(func_node, {"call_expression"}):
        func = node.child_by_field_name("function")
        if not func:
            continue
        callee_text = _node_text(func, source)
        if callee_text:
            # Use callee text as target — will be resolved by graph builder
            result.edges.append(ParsedEdge(
                source=func_id,
                target=f"ts_call::{callee_text}",
                type=EdgeType.CALLS,
                properties={"raw_callee": callee_text},
            ))


# ---------------------------------------------------------------------------
# Shared tree-sitter utilities
# ---------------------------------------------------------------------------

def _iter_nodes(root: Node, types: set[str]):
    """DFS iterator yielding all nodes of the given types."""
    cursor = root.walk()
    visited = set()
    stack = [root]
    while stack:
        node = stack.pop()
        if id(node) in visited:
            continue
        visited.add(id(node))
        if node.type in types:
            yield node
        stack.extend(reversed(node.children))


def _get_child_by_type(node: Node, type_name: str) -> Optional[Node]:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _node_text(node: Optional[Node], source: str) -> str:
    if node is None:
        return ""
    try:
        if node.text is not None:
            return node.text.decode("utf-8", errors="ignore")
    except Exception:
        pass
    try:
        start = node.start_byte
        end   = node.end_byte
        return source.encode("utf-8", errors="ignore")[start:end].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _child_text(node: Node, source: str, field: str) -> Optional[str]:
    child = node.child_by_field_name(field)
    return _node_text(child, source) if child else None


def _read_source_from_node(node: Node) -> str:
    try:
        if node.text is not None:
            return node.text.decode("utf-8", errors="ignore")
    except Exception:
        pass
    return ""



def _py_docstring(node: Node, source: str) -> Optional[str]:
    """Extract the first string literal in a function/class body as docstring."""
    body = _get_child_by_type(node, "block")
    if not body:
        return None
    for child in body.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    return _node_text(sub, source).strip('"""').strip("'''").strip('"').strip("'").strip()
    return None


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def _node_id(rel_path: str, name: str) -> str:
    return f"{rel_path}::{name}"


def _module_id(rel_path: str) -> str:
    return f"module::{rel_path}"


def _module_name(rel_path: str) -> str:
    return rel_path.replace(os.sep, ".").removesuffix(".py").removesuffix(".ts").removesuffix(".tsx")


def _dotted_to_path(
    dotted: str, repo_root: Path, from_rel: Optional[str] = None
) -> Optional[str]:
    """Convert 'backend.db.repository' or relative '.base' to repo-relative file path."""
    if not dotted:
        return None

    if dotted.startswith(".") and from_rel:
        lead_dots = len(dotted) - len(dotted.lstrip("."))
        remainder = dotted.lstrip(".")
        base_dir = (repo_root / from_rel).parent
        for _ in range(lead_dots - 1):
            base_dir = base_dir.parent
        if remainder:
            candidate = base_dir / Path(remainder.replace(".", "/"))
        else:
            candidate = base_dir
    else:
        candidate = repo_root / Path(dotted.replace(".", "/"))

    if (candidate / "__init__.py").exists():
        return str((candidate / "__init__.py").relative_to(repo_root))
    if candidate.with_suffix(".py").exists():
        return str(candidate.with_suffix(".py").relative_to(repo_root))
    if candidate.is_file() and candidate.exists():
        return str(candidate.relative_to(repo_root))
    return None


def _resolve_name(name: str, rel_path: str, import_map: dict[str, str]) -> str:
    """Resolve a class name to a node ID via import map or same-file fallback."""
    root_name = name.split(".")[0]
    if root_name in import_map:
        return _node_id(import_map[root_name], name.split(".")[-1])
    return _node_id(rel_path, name)

