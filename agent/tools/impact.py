"""
Tools: trace_impact, get_call_chain

trace_impact:
  Comprehensive impact analysis for a specific node.
  Returns upstream callers, downstream callees, exceptions raised, configs read.
  Wraps graph.queries.get_impact_analysis.

get_call_chain:
  Full multi-hop call chain from a node in either direction.
  Wraps graph.queries.get_call_chain + get_upstream_callers.
"""

from graph.connection import get_driver
from graph.queries import (
    get_impact_analysis,
    get_call_chain as _get_call_chain,
    get_upstream_callers,
)


def trace_impact(args: dict) -> dict:
    """
    Comprehensive impact analysis for a given node.

    Args:
        args:
            node_id (str): Node ID in format "<file>::<name>"
                           e.g. "backend/services/user_service.py::create_user"

    Returns:
        dict with keys:
            node_id (str)
            upstream_callers (list): Functions that call this node.
            downstream_callees (list): Functions this node calls.
            exceptions_raised (list): Exception nodes this function raises.
            configs_read (list): Config nodes this function reads.
            error (str | None)
    """
    node_id = args.get("node_id", "")
    if not node_id:
        return {"error": "node_id is required", "node_id": "", "upstream_callers": [],
                "downstream_callees": [], "exceptions_raised": [], "configs_read": []}

    try:
        driver = get_driver()
        result = get_impact_analysis(driver, node_id)
        return {
            "node_id": node_id,
            "upstream_callers": result.get("upstream_callers", []),
            "downstream_callees": result.get("downstream_callees", []),
            "exceptions_raised": result.get("exceptions_raised", []),
            "configs_read": result.get("configs_read", []),
            "error": None,
        }
    except Exception as e:
        return {
            "error": str(e),
            "node_id": node_id,
            "upstream_callers": [],
            "downstream_callees": [],
            "exceptions_raised": [],
            "configs_read": [],
        }


def get_call_chain(args: dict) -> dict:
    """
    Full multi-hop call chain from a node, upstream or downstream.

    Args:
        args:
            node_id (str): Node ID in format "<file>::<name>"
            direction (str): "upstream" (who calls it) or "downstream" (what it calls).
                             Default: "downstream"
            max_depth (int): Maximum traversal depth. Default: 4.

    Returns:
        dict with keys:
            node_id (str)
            direction (str)
            chain (list): Ordered list of node records in the chain.
            error (str | None)
    """
    node_id = args.get("node_id", "")
    direction = args.get("direction", "downstream")
    max_depth = args.get("max_depth", 4)

    if not node_id:
        return {"error": "node_id is required", "node_id": "", "direction": direction, "chain": []}

    if direction not in ("upstream", "downstream"):
        return {
            "error": f"direction must be 'upstream' or 'downstream', got '{direction}'",
            "node_id": node_id,
            "direction": direction,
            "chain": [],
        }

    try:
        driver = get_driver()
        if direction == "upstream":
            chain = get_upstream_callers(driver, node_id, max_depth=max_depth)
        else:
            chain = _get_call_chain(driver, node_id, max_depth=max_depth)

        return {
            "node_id": node_id,
            "direction": direction,
            "chain": chain,
            "error": None,
        }
    except Exception as e:
        return {
            "error": str(e),
            "node_id": node_id,
            "direction": direction,
            "chain": [],
        }
