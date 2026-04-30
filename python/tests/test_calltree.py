"""Tests for calltree build_tree line-number annotation."""

SIG_A = "<com.example.A: void foo()>"
SIG_B = "<com.example.B: void bar()>"
SIG_C = "<com.example.C: void baz()>"


def _cg(*pairs):
    """Build call graph dict from (caller, [callees]) pairs."""
    return dict(pairs)


class TestBuildTreeLineNumbers:
    def test_node_gets_line_numbers_from_index(self):
        from calltree import build_tree

        cg = _cg((SIG_A, []))
        line_index = {SIG_A: {"lineStart": 10, "lineEnd": 20}}
        node = build_tree(SIG_A, cg, _pat("com.example.A"), set(), {}, {}, line_index)
        assert node["lineStart"] == 10
        assert node["lineEnd"] == 20

    def test_node_without_index_entry_has_no_line_numbers(self):
        from calltree import build_tree

        cg = _cg((SIG_A, []))
        node = build_tree(SIG_A, cg, _pat("com.example.A"), set(), {}, {}, {})
        assert "lineStart" not in node
        assert "lineEnd" not in node

    def test_child_gets_line_numbers(self):
        from calltree import build_tree

        cg = _cg((SIG_A, [SIG_B]), (SIG_B, []))
        line_index = {SIG_B: {"lineStart": 5, "lineEnd": 7}}
        node = build_tree(SIG_A, cg, _pat("com.example"), set(), {}, {}, line_index)
        child = node["children"][0]
        assert child["lineStart"] == 5
        assert child["lineEnd"] == 7

    def test_cycle_node_gets_line_numbers(self):
        from calltree import build_tree

        # A calls A (cycle); cycle node should still get line numbers
        cg = _cg((SIG_A, [SIG_A]))
        line_index = {SIG_A: {"lineStart": 1, "lineEnd": 9}}
        node = build_tree(SIG_A, cg, _pat("com.example.A"), set(), {}, {}, line_index)
        cycle_child = node["children"][0]
        assert cycle_child.get("cycle") is True
        assert cycle_child["lineStart"] == 1

    def test_ref_node_gets_line_numbers(self):
        from calltree import build_tree

        # A -> B; B -> C; A -> C (second visit to C becomes ref)
        cg = _cg((SIG_A, [SIG_B, SIG_C]), (SIG_B, [SIG_C]), (SIG_C, []))
        line_index = {SIG_C: {"lineStart": 30, "lineEnd": 35}}
        ref_index: dict = {}
        node = build_tree(
            SIG_A, cg, _pat("com.example"), set(), {}, ref_index, line_index
        )
        # C appears twice: once fully built (child of B), once as ref (child of A)
        ref_nodes = [c for c in node["children"] if c.get("ref")]
        assert ref_nodes, "expected a ref node"
        assert ref_nodes[0]["lineStart"] == 30


def _pat(pattern):
    import re

    return re.compile(pattern)
