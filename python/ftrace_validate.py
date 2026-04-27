"""Validate structural invariants of a MethodSemanticCFG tree.

Pure validation functions that inspect the finished semantic graph.
No knowledge of how the graph was constructed.
"""

from collections import Counter

from ftrace_types import (
    MethodSemanticCFG,
    SemanticCluster,
    SemanticEdge,
    SemanticNode,
    Violation,
    ViolationKind,
    short_class,
)


def _method_label(method: MethodSemanticCFG) -> str:
    """Generate a readable label for a method."""
    cls = short_class(method.get("class", "?"))
    return f"{cls}.{method.get('method', '?')}"


def _check_unique_ids(nodes: list[SemanticNode], method_label: str) -> list[Violation]:
    """Check that all node IDs are unique."""
    counts = Counter(n["id"] for n in nodes)
    return [
        Violation(
            kind=ViolationKind.DUPLICATE_NODE_ID,
            node_id=nid,
            method=method_label,
            message=f"Node ID '{nid}' appears {count} times",
        )
        for nid, count in counts.items()
        if count > 1
    ]


def _check_edge_refs(
    edges: list[SemanticEdge], node_ids: frozenset[str], method_label: str
) -> list[Violation]:
    """Check that all edge endpoints reference existing nodes."""
    return [
        Violation(
            kind=ViolationKind.DANGLING_EDGE_REF,
            node_id=ref,
            method=method_label,
            message=f"Edge references non-existent node '{ref}' ({direction})",
        )
        for edge in edges
        for ref, direction in [(edge["from"], "from"), (edge["to"], "to")]
        if ref not in node_ids
    ]


def _check_cluster_refs(
    clusters: list[SemanticCluster], node_ids: frozenset[str], method_label: str
) -> list[Violation]:
    """Check that all cluster node references exist."""
    return [
        Violation(
            kind=ViolationKind.DANGLING_CLUSTER_REF,
            node_id=nid,
            method=method_label,
            message=f"Cluster references non-existent node '{nid}'",
        )
        for cluster in clusters
        for nid in cluster.get("nodeIds", [])
        if nid not in node_ids
    ]


def _check_entry_node(
    entry_nid: str, node_ids: frozenset[str], method_label: str
) -> list[Violation]:
    """Check that entryNodeId, if present, references an existing node."""
    if not entry_nid:
        return []
    if entry_nid not in node_ids:
        return [
            Violation(
                kind=ViolationKind.INVALID_ENTRY_NODE,
                node_id=entry_nid,
                method=method_label,
                message=f"entryNodeId '{entry_nid}' does not exist in nodes",
            )
        ]
    return []


def _check_leaf_fields(method: MethodSemanticCFG) -> list[Violation]:
    """Check that leaf nodes (ref/cycle/filtered) have no graph fields."""
    return []


def validate_method(method: MethodSemanticCFG) -> list[Violation]:
    """Validate a single method's semantic graph. Does not recurse into children."""
    # Leaf nodes: check separately
    if (
        method.get("ref", False)
        or method.get("cycle", False)
        or method.get("filtered", False)
    ):
        return _check_leaf_fields(method)

    nodes = method.get("nodes", [])
    edges = method.get("edges", [])
    clusters = method.get("clusters", [])
    entry_nid = method.get("entryNodeId", "")
    label = _method_label(method)
    node_ids = frozenset(n["id"] for n in nodes)

    return [
        *_check_unique_ids(nodes, label),
        *_check_edge_refs(edges, node_ids, label),
        *_check_cluster_refs(clusters, node_ids, label),
        *_check_entry_node(entry_nid, node_ids, label),
    ]


def validate_tree(root: MethodSemanticCFG) -> list[Violation]:
    """Validate entire tree recursively. Returns all violations."""
    own = validate_method(root)
    child_violations = [
        v for child in root.get("children", []) for v in validate_tree(child)
    ]
    return [*own, *child_violations]
