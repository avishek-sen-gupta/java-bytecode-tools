"""Smoke tests for shared type definitions."""

from ftrace_types import (
    RawStmt,
    MergedStmt,
    RawBlock,
    RawBlockEdge,
    RawTrap,
    ClusterAssignment,
    BlockAliases,
    SemanticNode,
    SemanticEdge,
    SemanticCluster,
    ExceptionEdge,
    SlicedTrace,
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
        b: RawBlock = {"id": "B0", "stmts": [{"line": 5}]}
        assert b["id"] == "B0"

    def test_raw_block_has_no_successors(self):
        import typing

        hints = typing.get_type_hints(RawBlock)
        assert "successors" not in hints

    def test_raw_block_edge_unconditional(self):
        e: RawBlockEdge = {"fromBlock": "B0", "toBlock": "B1"}
        assert e["fromBlock"] == "B0"
        assert e["toBlock"] == "B1"
        assert "label" not in e

    def test_raw_block_edge_with_label(self):
        e: RawBlockEdge = {"fromBlock": "B0", "toBlock": "B1", "label": "T"}
        assert e["label"] == "T"

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

    def test_sliced_trace_type(self):
        """SlicedTrace has slice and refIndex fields."""
        st: SlicedTrace = {
            "slice": {"method": "foo", "children": []},
            "refIndex": {"<Svc: void foo()>": {"method": "foo"}},
        }
        assert st["slice"]["method"] == "foo"
        assert "<Svc: void foo()>" in st["refIndex"]

    def test_method_cfg_has_edges_field(self):
        import typing
        from ftrace_types import MethodCFG

        hints = typing.get_type_hints(MethodCFG)
        assert "edges" in hints

    def test_str_enum_equals_string(self):
        assert NodeKind.PLAIN == "plain"
        assert ClusterRole.TRY == "try"
        assert BranchLabel.T == "T"


class TestShortClass:
    def test_fully_qualified(self):
        from ftrace_types import short_class

        assert short_class("java.lang.RuntimeException") == "RuntimeException"

    def test_deeply_nested(self):
        from ftrace_types import short_class

        assert short_class("com.example.service.UserService") == "UserService"

    def test_no_package(self):
        from ftrace_types import short_class

        assert short_class("Foo") == "Foo"

    def test_empty_string(self):
        from ftrace_types import short_class

        assert short_class("") == ""

    def test_single_dot(self):
        from ftrace_types import short_class

        assert short_class("pkg.Class") == "Class"


class TestNodeCounter:
    def test_default_value(self):
        from ftrace_types import NodeCounter

        c = NodeCounter()
        assert c.value == 0

    def test_custom_value(self):
        from ftrace_types import NodeCounter

        c = NodeCounter(42)
        assert c.value == 42

    def test_advance(self):
        from ftrace_types import NodeCounter

        c = NodeCounter(10)
        c2 = c.advance(5)
        assert c2.value == 15

    def test_advance_is_immutable(self):
        from ftrace_types import NodeCounter

        c = NodeCounter(10)
        c.advance(5)
        assert c.value == 10

    def test_frozen(self):
        from ftrace_types import NodeCounter
        import dataclasses

        c = NodeCounter(10)
        with __import__("pytest").raises(dataclasses.FrozenInstanceError):
            c.value = 20
