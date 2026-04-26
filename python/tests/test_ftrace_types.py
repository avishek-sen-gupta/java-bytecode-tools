"""Smoke tests for shared type definitions."""

from ftrace_types import (
    RawStmt,
    MergedStmt,
    RawBlock,
    RawTrap,
    ClusterAssignment,
    BlockAliases,
    SemanticNode,
    SemanticEdge,
    SemanticCluster,
    ExceptionEdge,
    NodeKind,
    ClusterRole,
    BranchLabel,
)


class TestTypeConstructors:
    def test_raw_stmt_with_call(self):
        stmt: RawStmt = {"line": 9, "call": "Foo.bar"}
        assert stmt["line"] == 9
        assert stmt["call"] == "Foo.bar"

    def test_raw_stmt_minimal(self):
        stmt: RawStmt = {"line": 5}
        assert stmt["line"] == 5

    def test_merged_stmt(self):
        m: MergedStmt = {"line": 9, "calls": ["Foo.bar"], "branches": [], "assigns": []}
        assert m["calls"] == ["Foo.bar"]

    def test_raw_block(self):
        b: RawBlock = {"id": "B0", "stmts": [{"line": 5}], "successors": ["B1"]}
        assert b["id"] == "B0"

    def test_raw_trap(self):
        t: RawTrap = {
            "handler": "B3",
            "type": "java.lang.RuntimeException",
            "coveredBlocks": ["B0", "B1"],
            "handlerBlocks": ["B3", "B4"],
        }
        assert t["handler"] == "B3"

    def test_cluster_assignment(self):
        a: ClusterAssignment = {"kind": ClusterRole.TRY, "trapIndex": 0}
        assert a["kind"] == ClusterRole.TRY

    def test_semantic_node(self):
        n: SemanticNode = {
            "id": "n0",
            "lines": [6],
            "kind": NodeKind.PLAIN,
            "label": ["L6"],
        }
        assert n["kind"] == NodeKind.PLAIN

    def test_semantic_edge_no_branch(self):
        e: SemanticEdge = {"from": "n0", "to": "n1"}
        assert "branch" not in e

    def test_semantic_edge_with_branch(self):
        e: SemanticEdge = {"from": "n0", "to": "n1", "branch": BranchLabel.T}
        assert e["branch"] == BranchLabel.T

    def test_semantic_cluster(self):
        c: SemanticCluster = {
            "trapType": "RuntimeException",
            "role": ClusterRole.TRY,
            "nodeIds": ["n0", "n1"],
        }
        assert c["role"] == ClusterRole.TRY

    def test_exception_edge(self):
        ee: ExceptionEdge = {
            "from": "n0",
            "to": "n5",
            "trapType": "RuntimeException",
            "fromCluster": 0,
            "toCluster": 1,
        }
        assert ee["trapType"] == "RuntimeException"

    def test_node_kind_values(self):
        assert list(NodeKind) == [
            NodeKind.PLAIN,
            NodeKind.CALL,
            NodeKind.BRANCH,
            NodeKind.ASSIGN,
            NodeKind.CYCLE,
            NodeKind.REF,
            NodeKind.FILTERED,
        ]

    def test_cluster_role_values(self):
        assert list(ClusterRole) == [ClusterRole.TRY, ClusterRole.HANDLER]

    def test_branch_label_values(self):
        assert list(BranchLabel) == [BranchLabel.T, BranchLabel.F]

    def test_str_enum_equals_string(self):
        assert NodeKind.PLAIN == "plain"
        assert ClusterRole.TRY == "try"
        assert BranchLabel.T == "T"
