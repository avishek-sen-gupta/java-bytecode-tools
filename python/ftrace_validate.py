"""Validate structural invariants of a MethodSemanticCFG tree.

Pure validation functions that inspect the finished semantic graph.
No knowledge of how the graph was constructed.
"""

from collections import Counter
from functools import reduce

from ftrace_types import (
    ExceptionEdge,
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


def _check_branch_node(
    nid: str, node_outgoing: list[SemanticEdge], method_label: str
) -> list[Violation]:
    """Check that a branch node has exactly one 'T' and one 'F' edge."""
    labels = sorted(e.get("branch", "") for e in node_outgoing)
    if labels == ["F", "T"]:
        return []
    return [
        Violation(
            kind=ViolationKind.BRANCH_EDGE_VIOLATION,
            node_id=nid,
            method=method_label,
            message=f"Branch node must have exactly one 'T' and one 'F' edge, got labels {labels}",
        )
    ]


def _check_non_branch_node(
    nid: str, node_outgoing: list[SemanticEdge], method_label: str
) -> list[Violation]:
    """Check that a non-branch node has at most 1 outgoing edge, never labeled."""
    count_violation = (
        [
            Violation(
                kind=ViolationKind.NON_BRANCH_EDGE_VIOLATION,
                node_id=nid,
                method=method_label,
                message=f"Non-branch node has {len(node_outgoing)} outgoing edges, expected at most 1",
            )
        ]
        if len(node_outgoing) > 1
        else []
    )
    branch_label = node_outgoing[0].get("branch", "") if node_outgoing else ""
    label_violation = (
        [
            Violation(
                kind=ViolationKind.NON_BRANCH_EDGE_VIOLATION,
                node_id=nid,
                method=method_label,
                message=f"Non-branch node has labeled edge ('{branch_label}'), should be unlabeled",
            )
        ]
        if branch_label
        else []
    )
    return [*count_violation, *label_violation]


def _check_branch_edges(
    nodes: list[SemanticNode], edges: list[SemanticEdge], method_label: str
) -> list[Violation]:
    """Check branch node edge invariants.

    - Branch nodes must have exactly 2 outgoing edges, one labeled 'T' and one 'F'.
    - Non-branch nodes must have at most 1 outgoing edge, never labeled.
    """

    # Build outgoing edges per node using reduce
    def add_edge(acc: dict[str, list[SemanticEdge]], edge: SemanticEdge):
        from_id = edge["from"]
        return {**acc, from_id: [*acc.get(from_id, []), edge]}

    outgoing = reduce(add_edge, edges, {})

    return [
        v
        for node in nodes
        for v in (
            _check_branch_node(node["id"], outgoing.get(node["id"], []), method_label)
            if node.get("kind", "") == "branch"
            else _check_non_branch_node(
                node["id"], outgoing.get(node["id"], []), method_label
            )
        )
    ]


def _check_reachability(
    nodes: list[SemanticNode],
    edges: list[SemanticEdge],
    exception_edges: list[ExceptionEdge],
    entry_nid: str,
    method_label: str,
) -> list[Violation]:
    """Check that all nodes except entry are reachable.

    A node is reachable if it has at least one incoming edge from edges or exceptionEdges.
    """
    nodes_with_incoming = frozenset(
        [*(e["to"] for e in edges), *(e["to"] for e in exception_edges)]
    )

    return [
        Violation(
            kind=ViolationKind.NO_INCOMING_EDGE,
            node_id=n["id"],
            method=method_label,
            message=f"Node '{n['id']}' has no incoming edges and is not the entry node",
        )
        for n in nodes
        if n["id"] != entry_nid and n["id"] not in nodes_with_incoming
    ]


def _check_leaf_fields(method: MethodSemanticCFG) -> list[Violation]:
    """Check that leaf nodes (ref/cycle/filtered) have no graph fields.

    Leaf nodes must not have: nodes, edges, clusters, exceptionEdges.
    """
    is_leaf = (
        method.get("ref", False)
        or method.get("cycle", False)
        or method.get("filtered", False)
    )
    if not is_leaf:
        return []

    label = _method_label(method)
    forbidden_fields = ["nodes", "edges", "clusters", "exceptionEdges"]

    return [
        Violation(
            kind=ViolationKind.LEAF_HAS_GRAPH_FIELDS,
            node_id="",
            method=label,
            message=f"Leaf node has forbidden field '{field}'",
        )
        for field in forbidden_fields
        if method.get(field)
    ]


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
    exception_edges = method.get("exceptionEdges", [])
    entry_nid = method.get("entryNodeId", "")
    label = _method_label(method)
    node_ids = frozenset(n["id"] for n in nodes)

    return [
        *_check_unique_ids(nodes, label),
        *_check_edge_refs(edges, node_ids, label),
        *_check_cluster_refs(clusters, node_ids, label),
        *_check_entry_node(entry_nid, node_ids, label),
        *_check_branch_edges(nodes, edges, label),
        *_check_reachability(nodes, edges, exception_edges, entry_nid, label),
    ]


def validate_tree(root: MethodSemanticCFG) -> list[Violation]:
    """Validate entire tree recursively. Returns all violations."""
    own = validate_method(root)
    child_violations = [
        v for child in root.get("children", []) for v in validate_tree(child)
    ]
    return [*own, *child_violations]


def main():
    """CLI entry point for ftrace-validate UNIX pipeline tool.

    Reads semantic JSON from stdin/file, validates invariants, logs violations
    to stderr, and passes through the JSON unchanged to stdout/file.

    Exit code 0 if no violations, 1 if violations found.
    """
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Validate semantic graph invariants and detect structural bugs."
    )
    parser.add_argument(
        "--input", type=Path, help="Input semantic JSON file (default: stdin)"
    )
    parser.add_argument(
        "--output", type=Path, help="Output JSON file (default: stdout)"
    )
    args = parser.parse_args()

    # Read input
    if args.input:
        with open(args.input) as f:
            root = json.load(f)
    else:
        root = json.load(sys.stdin)

    # Validate
    violations = validate_tree(root)

    # Log violations to stderr
    if violations:
        for v in violations:
            method = v["method"]
            node_id = v["node_id"]
            kind = v["kind"]
            message = v["message"]
            location = f"{method}:{node_id}" if node_id else method
            print(f"[{kind}] {location} — {message}", file=sys.stderr)

    # Write output (pass-through)
    output = json.dumps(root, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote semantic graph to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Exit with appropriate code
    sys.exit(1 if violations else 0)


if __name__ == "__main__":
    main()
