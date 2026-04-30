"""Tests for calltree callsite line annotation."""

import re

SIG_A = "<com.example.A: void foo()>"
SIG_B = "<com.example.B: void bar()>"
SIG_C = "<com.example.C: void baz()>"


def _cg(edges: list[tuple[str, list[str]]]) -> dict[str, list[str]]:
    return dict(edges)


def _pat(pattern: str) -> re.Pattern:
    return re.compile(pattern)


class TestBuildTreeCallsiteLines:
    def test_child_gets_callsite_line_when_present(self):
        from calltree import build_tree

        cg = _cg([(SIG_A, [SIG_B])])
        callsites = {SIG_A: {SIG_B: 42}}
        node = build_tree(SIG_A, cg, _pat("com.example"), set(), {}, {}, callsites, "")
        assert node["children"][0]["callSiteLine"] == 42

    def test_no_callsite_line_when_not_in_callsites(self):
        from calltree import build_tree

        cg = _cg([(SIG_A, [SIG_B])])
        node = build_tree(SIG_A, cg, _pat("com.example"), set(), {}, {}, {}, "")
        assert "callSiteLine" not in node["children"][0]

    def test_root_has_no_callsite_line(self):
        from calltree import build_tree

        cg = _cg([(SIG_A, [])])
        node = build_tree(SIG_A, cg, _pat("com.example"), set(), {}, {}, {}, "")
        assert "callSiteLine" not in node

    def test_callsite_line_propagates_to_grandchildren(self):
        from calltree import build_tree

        cg = _cg([(SIG_A, [SIG_B]), (SIG_B, [SIG_C])])
        callsites = {SIG_A: {SIG_B: 10}, SIG_B: {SIG_C: 20}}
        node = build_tree(SIG_A, cg, _pat("com.example"), set(), {}, {}, callsites, "")
        assert node["children"][0]["callSiteLine"] == 10
        assert node["children"][0]["children"][0]["callSiteLine"] == 20

    def test_children_sorted_by_callsite_line(self):
        from calltree import build_tree

        cg = _cg([(SIG_A, [SIG_B, SIG_C])])
        callsites = {SIG_A: {SIG_B: 20, SIG_C: 10}}
        node = build_tree(SIG_A, cg, _pat("com.example"), set(), {}, {}, callsites, "")
        lines = [c["callSiteLine"] for c in node["children"]]
        assert lines == [10, 20]

    def test_children_without_callsite_line_sort_last(self):
        from calltree import build_tree

        cg = _cg([(SIG_A, [SIG_B, SIG_C])])
        callsites = {SIG_A: {SIG_C: 5}}  # SIG_B has no callsite line
        node = build_tree(SIG_A, cg, _pat("com.example"), set(), {}, {}, callsites, "")
        sigs = [c["methodSignature"] for c in node["children"]]
        assert sigs == [SIG_C, SIG_B]

    def test_does_not_mutate_callsites_input(self):
        from calltree import build_tree

        cg = _cg([(SIG_A, [SIG_B])])
        callsites = {SIG_A: {SIG_B: 42}}
        original = {SIG_A: {SIG_B: 42}}
        build_tree(SIG_A, cg, _pat("com.example"), set(), {}, {}, callsites, "")
        assert callsites == original
