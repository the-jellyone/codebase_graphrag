"""
Single source of truth for the Neo4j Knowledge Graph schema.

Imported by every tool that generates or relies on Cypher queries:
  - run_cypher (injected into Cypher generation prompt)
  - list_by_pattern (presets reference exact labels/types)
  - trace_impact, get_call_chain (reference relationship types)

Schema changes here automatically propagate to all tools.
"""

GRAPH_SCHEMA = """
## Neo4j Knowledge Graph Schema

### Node Labels and Properties
  Function  { id, name, file, line, docstring, source_code, embedding }
  Class     { id, name, file, line, docstring, source_code, embedding }
  Module    { id, name, file_path }
  Exception { id, name }
  Config    { id, name, value }

### Relationship Types
  (Function)-[:CALLS]        ->(Function)
  (Module)  -[:IMPORTS]      ->(Module)
  (Class)   -[:INHERITS]     ->(Class)
  (Function)-[:RAISES]       ->(Exception)
  (Class)   -[:HAS_METHOD]   ->(Function)
  (Function)-[:READS]        ->(Config)
  (Module|Class)-[:CONTAINS] ->(Function|Class)
  (Module)  -[:DEFINES_TYPE] ->(Class)
  (Function)-[:USES_TYPE]    ->(Class)

### Node ID Format
  Node IDs follow: "<relative_file_path>::<entity_name>"
  Example: "backend/services/user_service.py::create_user"
  Module IDs follow: "module::<relative_file_path>"
  Example: "module::backend/services/user_service.py"
  Exception IDs follow: "exception::<ExceptionName>"
  Config IDs follow: "config::<config.KEY>" or "config::env.<KEY>"
"""

# Short tool descriptions injected into Orchestrator prompt
TOOL_DESCRIPTIONS = {
    "graph_rag_search": (
        "Semantic + structural retrieval. Use for 'understand/explain' questions. "
        "Embeds the query, finds seed nodes via vector similarity, traverses the graph "
        "for related context. Args: {query: str}"
    ),
    "run_cypher": (
        "Direct structural queries. Use for 'list/count/find all X' questions. "
        "Describe what you want in plain English — the tool generates and runs the Cypher. "
        "Args: {intent: str}"
    ),
    "list_by_pattern": (
        "Common structural presets. Use when the question matches a known pattern. "
        "Presets: no_docstring, high_method_count, unused_function, high_coupling, no_test_coverage. "
        "Args: {pattern: str, limit: int (optional, default 10)}"
    ),
    "get_file_content": (
        "Fetch raw source code of a file. Use when you need the full implementation. "
        "Args: {file_path: str}"
    ),
    "trace_impact": (
        "Comprehensive impact analysis for a specific node. Returns upstream callers, "
        "downstream callees, exceptions raised, and config reads. "
        "Args: {node_id: str}"
    ),
    "get_call_chain": (
        "Full multi-hop call chain from a node — upstream (who calls it) or downstream (what it calls). "
        "Args: {node_id: str, direction: 'upstream'|'downstream', max_depth: int (optional, default 4)}"
    ),
    "suggest_fix": (
        "Text-only diagnosis and recommendation for a code issue. No file writes. "
        "Args: {context: str, node_id: str (optional)}"
    ),
}
