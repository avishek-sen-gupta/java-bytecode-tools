"""Tests for semantic graph validation."""

from ftrace_types import (
    NodeKind,
    ViolationKind,
)


def _make_method(
    nodes=(),
    edges=(),
    clusters=(),
    exception_edges=(),
    entry_node_id="",
    cls="com.example.Svc",
    method="handle",
):
    """Build a minimal MethodSemanticCFG for validation testing."""
    result = {
        "class": cls,
        "method": method,
        "methodSignature": f"<{cls}: void {method}()>",
        "nodes": list(nodes),
        "edges": list(edges),
        "clusters": list(clusters),
        "exceptionEdges": list(exception_edges),
        "children": [],
    }
    if entry_node_id:
        result["entryNodeId"] = entry_node_id
    return result


def _node(nid, kind=NodeKind.PLAIN):
    return {"id": nid, "lines": [1], "kind": kind, "label": ["L1"]}


class TestCheckUniqueIds:
    def test_no_duplicates_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(nodes=[_node("n0"), _node("n1")], entry_node_id="n0")
        assert [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.DUPLICATE_NODE_ID
        ] == []

    def test_duplicate_ids_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(nodes=[_node("n0"), _node("n0")], entry_node_id="n0")
        violations = [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.DUPLICATE_NODE_ID
        ]
        assert len(violations) == 1
        assert violations[0]["node_id"] == "n0"


class TestCheckEdgeRefs:
    def test_valid_edges_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0"), _node("n1")],
            edges=[{"from": "n0", "to": "n1"}],
            entry_node_id="n0",
        )
        assert [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.DANGLING_EDGE_REF
        ] == []

    def test_dangling_from_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0")],
            edges=[{"from": "n99", "to": "n0"}],
            entry_node_id="n0",
        )
        violations = [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.DANGLING_EDGE_REF
        ]
        assert len(violations) == 1
        assert "n99" in violations[0]["message"]

    def test_dangling_to_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0")],
            edges=[{"from": "n0", "to": "n99"}],
            entry_node_id="n0",
        )
        violations = [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.DANGLING_EDGE_REF
        ]
        assert len(violations) == 1
        assert "n99" in violations[0]["message"]


class TestCheckClusterRefs:
    def test_valid_cluster_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0")],
            clusters=[{"trapType": "Exception", "role": "try", "nodeIds": ["n0"]}],
            entry_node_id="n0",
        )
        assert [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.DANGLING_CLUSTER_REF
        ] == []

    def test_dangling_cluster_ref_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0")],
            clusters=[
                {"trapType": "Exception", "role": "try", "nodeIds": ["n0", "n99"]}
            ],
            entry_node_id="n0",
        )
        violations = [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.DANGLING_CLUSTER_REF
        ]
        assert len(violations) == 1
        assert "n99" in violations[0]["message"]


class TestCheckEntryNode:
    def test_valid_entry_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(nodes=[_node("n0")], entry_node_id="n0")
        assert [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.INVALID_ENTRY_NODE
        ] == []

    def test_invalid_entry_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(nodes=[_node("n0")], entry_node_id="n99")
        violations = [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.INVALID_ENTRY_NODE
        ]
        assert len(violations) == 1
        assert "n99" in violations[0]["message"]

    def test_no_entry_no_nodes_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(nodes=[], entry_node_id="")
        assert [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.INVALID_ENTRY_NODE
        ] == []


class TestCheckBranchEdges:
    def test_valid_branch_node_returns_empty(self):
        """Branch node with exactly T and F outgoing edges."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.BRANCH), _node("n1"), _node("n2")],
            edges=[
                {"from": "n0", "to": "n1", "branch": "T"},
                {"from": "n0", "to": "n2", "branch": "F"},
            ],
            entry_node_id="n0",
        )
        assert [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.BRANCH_EDGE_VIOLATION
        ] == []

    def test_branch_node_missing_label_reported(self):
        """Branch node with only one outgoing edge."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.BRANCH), _node("n1")],
            edges=[{"from": "n0", "to": "n1", "branch": "T"}],
            entry_node_id="n0",
        )
        violations = [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.BRANCH_EDGE_VIOLATION
        ]
        assert len(violations) == 1
        assert "n0" in violations[0]["node_id"]

    def test_branch_node_with_unlabeled_edge_reported(self):
        """Branch node with an unlabeled outgoing edge."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.BRANCH), _node("n1")],
            edges=[{"from": "n0", "to": "n1"}],
            entry_node_id="n0",
        )
        violations = [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.BRANCH_EDGE_VIOLATION
        ]
        assert len(violations) >= 1

    def test_branch_converging_to_same_target_valid(self):
        """Branch node with T and F both pointing to same node is valid."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.BRANCH), _node("n1")],
            edges=[
                {"from": "n0", "to": "n1", "branch": "T"},
                {"from": "n0", "to": "n1", "branch": "F"},
            ],
            entry_node_id="n0",
        )
        assert [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.BRANCH_EDGE_VIOLATION
        ] == []

    def test_non_branch_with_labeled_edge_reported(self):
        """Plain node must not have T/F labeled edges."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.PLAIN), _node("n1")],
            edges=[{"from": "n0", "to": "n1", "branch": "T"}],
            entry_node_id="n0",
        )
        violations = [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.NON_BRANCH_EDGE_VIOLATION
        ]
        assert len(violations) >= 1

    def test_non_branch_with_multiple_outgoing_reported(self):
        """Plain node must not have more than one outgoing edge."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.CALL), _node("n1"), _node("n2")],
            edges=[
                {"from": "n0", "to": "n1"},
                {"from": "n0", "to": "n2"},
            ],
            entry_node_id="n0",
        )
        violations = [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.NON_BRANCH_EDGE_VIOLATION
        ]
        assert len(violations) == 1

    def test_non_branch_with_single_unlabeled_edge_valid(self):
        """Plain node with one unlabeled outgoing edge is valid."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0"), _node("n1")],
            edges=[{"from": "n0", "to": "n1"}],
            entry_node_id="n0",
        )
        assert [
            v
            for v in validate_method(m)
            if v["kind"] == ViolationKind.NON_BRANCH_EDGE_VIOLATION
        ] == []
