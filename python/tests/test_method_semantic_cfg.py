"""Tests for MethodSemanticCFG type extraction from MethodCFG."""

import typing


class TestMethodSemanticCFGType:
    def test_importable(self):
        from ftrace_types import MethodSemanticCFG

        assert MethodSemanticCFG is not None

    def test_has_identity_fields(self):
        from ftrace_types import MethodSemanticCFG

        hints = typing.get_type_hints(MethodSemanticCFG)
        assert "method" in hints
        assert "methodSignature" in hints

    def test_has_semantic_graph_fields(self):
        from ftrace_types import MethodSemanticCFG

        hints = typing.get_type_hints(MethodSemanticCFG)
        for field in ("nodes", "edges", "clusters", "exceptionEdges", "entryNodeId"):
            assert field in hints, f"MethodSemanticCFG missing {field}"

    def test_has_leaf_markers(self):
        from ftrace_types import MethodSemanticCFG

        hints = typing.get_type_hints(MethodSemanticCFG)
        for field in ("ref", "cycle", "filtered", "callSiteLine"):
            assert field in hints, f"MethodSemanticCFG missing {field}"

    def test_has_recursive_children(self):
        from ftrace_types import MethodSemanticCFG

        hints = typing.get_type_hints(MethodSemanticCFG)
        assert "children" in hints

    def test_no_raw_fields(self):
        from ftrace_types import MethodSemanticCFG

        hints = typing.get_type_hints(MethodSemanticCFG)
        for field in (
            "blocks",
            "traps",
            "sourceTrace",
            "mergedSourceTrace",
            "clusterAssignment",
            "blockAliases",
        ):
            assert field not in hints, f"MethodSemanticCFG should not have {field}"


class TestMethodCFGNoSemanticFields:
    def test_no_semantic_graph_fields(self):
        from ftrace_types import MethodCFG

        hints = typing.get_type_hints(MethodCFG)
        for field in ("nodes", "clusters", "exceptionEdges"):
            assert field not in hints, f"MethodCFG should no longer have {field}"


class TestBuildSemanticGraphReturnsNewType:
    def test_return_type_annotation(self):
        from ftrace_semantic import build_semantic_graph_pass

        hints = typing.get_type_hints(build_semantic_graph_pass)
        assert hints["return"].__name__ == "MethodSemanticCFG"

    def test_transform_return_type_annotation(self):
        from ftrace_semantic import transform

        hints = typing.get_type_hints(transform)
        assert hints["return"].__name__ == "MethodSemanticCFG"


class TestDotAcceptsNewType:
    def test_build_dot_parameter_type(self):
        from ftrace_to_dot import build_dot

        hints = typing.get_type_hints(build_dot)
        assert hints["root"].__name__ == "MethodSemanticCFG"
