"""Tests for calltree flat {nodes, calls} graph builder."""

import re

SIG_A = "<com.example.A: void foo()>"
SIG_B = "<com.example.B: void bar()>"
SIG_C = "<com.example.C: void baz()>"
SIG_D = "<com.example.D: void qux()>"

METHOD_LINES = {
    SIG_A: {"lineStart": 10, "lineEnd": 20},
    SIG_B: {"lineStart": 30, "lineEnd": 40},
    SIG_C: {"lineStart": 50, "lineEnd": 60},
    SIG_D: {"lineStart": 70, "lineEnd": 80},
}


def _cg(edges: list[tuple[str, list[str]]]) -> dict[str, list[str]]:
    return dict(edges)


def _pat(pattern: str) -> re.Pattern:
    return re.compile(pattern)


class TestBuildGraph:
    def test_single_root_no_children_emits_node(self):
        from calltree import build_graph

        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            METHOD_LINES,
            "",
        )
        assert SIG_A in nodes
        assert nodes[SIG_A]["class"] == "com.example.A"
        assert nodes[SIG_A]["method"] == "foo"
        assert nodes[SIG_A]["lineStart"] == 10
        assert nodes[SIG_A]["lineEnd"] == 20
        assert nodes[SIG_A]["sourceLineCount"] == 11

    def test_normal_call_edge_emitted(self):
        from calltree import build_graph

        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_B]), (SIG_B, [])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {SIG_A: {SIG_B: 15}},
            METHOD_LINES,
            "",
        )
        assert any(c["from"] == SIG_A and c["to"] == SIG_B for c in calls)

    def test_callsite_line_on_edge(self):
        from calltree import build_graph

        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_B]), (SIG_B, [])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {SIG_A: {SIG_B: 15}},
            METHOD_LINES,
            "",
        )
        edge = next(c for c in calls if c["from"] == SIG_A and c["to"] == SIG_B)
        assert edge["callSiteLine"] == 15

    def test_cycle_edge_flagged(self):
        from calltree import build_graph

        # A → B → A (cycle)
        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_B]), (SIG_B, [SIG_A])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            METHOD_LINES,
            "",
        )
        cycle_edges = [c for c in calls if c.get("cycle")]
        assert any(c["to"] == SIG_A for c in cycle_edges)

    def test_out_of_scope_callee_emits_filtered_edge(self):
        from calltree import build_graph

        # SIG_D is in "other.pkg", not matching "com.example"
        SIG_OTHER = "<other.pkg.X: void run()>"
        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_OTHER])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            {},
            "",
        )
        filtered = [c for c in calls if c.get("filtered")]
        assert any(c["to"] == SIG_OTHER for c in filtered)
        # Filtered sig must not appear in nodes
        assert SIG_OTHER not in nodes

    def test_deduplicated_nodes_via_visited(self):
        from calltree import build_graph

        # A → B, A → C, B → C (C reached twice)
        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_B, SIG_C]), (SIG_B, [SIG_C]), (SIG_C, [])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            METHOD_LINES,
            "",
        )
        assert list(nodes.keys()).count(SIG_C) == 1

    def test_no_linestart_when_method_lines_missing(self):
        from calltree import build_graph

        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            {},
            "",
        )
        assert "lineStart" not in nodes[SIG_A]

    def test_does_not_mutate_inputs(self):
        from calltree import build_graph

        cg = _cg([(SIG_A, [SIG_B]), (SIG_B, [])])
        callsites_in = {SIG_A: {SIG_B: 15}}
        orig_callsites = {SIG_A: {SIG_B: 15}}
        nodes, calls = {}, []
        build_graph(
            SIG_A,
            cg,
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            callsites_in,
            METHOD_LINES,
            "",
        )
        assert callsites_in == orig_callsites

    def test_node_has_node_type_java_method(self):
        from calltree import build_graph

        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            METHOD_LINES,
            "",
        )
        assert nodes[SIG_A]["node_type"] == "java_method"

    def test_normal_edge_has_edge_info(self):
        from calltree import build_graph

        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_B]), (SIG_B, [])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            METHOD_LINES,
            "",
        )
        edge = next(c for c in calls if c["from"] == SIG_A and c["to"] == SIG_B)
        assert edge["edge_info"] == {}

    def test_cycle_edge_has_edge_info(self):
        from calltree import build_graph

        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_B]), (SIG_B, [SIG_A])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            METHOD_LINES,
            "",
        )
        cycle_edge = next(c for c in calls if c.get("cycle"))
        assert cycle_edge["edge_info"] == {}

    def test_filtered_edge_has_edge_info(self):
        from calltree import build_graph

        SIG_OTHER = "<other.pkg.X: void run()>"
        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_OTHER])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            {},
            "",
        )
        filtered_edge = next(c for c in calls if c.get("filtered"))
        assert filtered_edge["edge_info"] == {}
