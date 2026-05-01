"""Tests for frames.py — Python backward BFS tracer."""

import re

SIG_MAIN = "<com.example.App: void main(String[])>"
SIG_SVC = "<com.example.Svc: void handle()>"
SIG_DAO = "<com.example.Dao: void save()>"
SIG_UTIL = "<com.example.Util: int compute()>"

METHOD_LINES = {
    SIG_MAIN: {"line_start": 5, "line_end": 15},
    SIG_SVC: {"line_start": 20, "line_end": 40},
    SIG_DAO: {"line_start": 50, "line_end": 70},
    SIG_UTIL: {"line_start": 80, "line_end": 90},
}

# call graph: main→svc→dao, main→util
CALLEES = {
    SIG_MAIN: [SIG_SVC, SIG_UTIL],
    SIG_SVC: [SIG_DAO],
}

CALLSITES = {
    SIG_MAIN: {SIG_SVC: 10, SIG_UTIL: 12},
    SIG_SVC: {SIG_DAO: 35},
}


class TestFindTargetSig:
    def test_finds_sig_by_class_and_line_in_range(self):
        from rev_calltree import find_target_sig

        sig = find_target_sig("com.example.Dao", 55, METHOD_LINES)
        assert sig == SIG_DAO

    def test_returns_empty_when_class_not_found(self):
        from rev_calltree import find_target_sig

        sig = find_target_sig("com.example.Missing", 55, METHOD_LINES)
        assert sig == ""

    def test_returns_empty_when_line_out_of_range(self):
        from rev_calltree import find_target_sig

        sig = find_target_sig("com.example.Dao", 99, METHOD_LINES)
        assert sig == ""

    def test_boundary_line_start_inclusive(self):
        from rev_calltree import find_target_sig

        sig = find_target_sig("com.example.Dao", 50, METHOD_LINES)
        assert sig == SIG_DAO

    def test_boundary_line_end_inclusive(self):
        from rev_calltree import find_target_sig

        sig = find_target_sig("com.example.Dao", 70, METHOD_LINES)
        assert sig == SIG_DAO


class TestBuildReverseMap:
    def test_inverts_callees(self):
        from rev_calltree import build_reverse_map

        callers = build_reverse_map(CALLEES)
        assert SIG_MAIN in callers.get(SIG_SVC, [])
        assert SIG_MAIN in callers.get(SIG_UTIL, [])
        assert SIG_SVC in callers.get(SIG_DAO, [])

    def test_root_has_no_entry(self):
        from rev_calltree import build_reverse_map

        callers = build_reverse_map(CALLEES)
        assert SIG_MAIN not in callers

    def test_does_not_mutate_input(self):
        from rev_calltree import build_reverse_map

        original = {SIG_MAIN: [SIG_SVC]}
        build_reverse_map(original)
        assert original == {SIG_MAIN: [SIG_SVC]}


class TestBfsBackward:
    def test_finds_reachable_callers(self):
        from rev_calltree import bfs_backward

        callers_map = {SIG_SVC: [SIG_MAIN], SIG_DAO: [SIG_SVC]}
        reachable = bfs_backward(SIG_DAO, callers_map, max_depth=10)
        assert SIG_SVC in reachable
        assert SIG_MAIN in reachable

    def test_stops_at_max_depth(self):
        from rev_calltree import bfs_backward

        # main→svc→dao, depth=1 from dao → only svc reachable
        callers_map = {SIG_SVC: [SIG_MAIN], SIG_DAO: [SIG_SVC]}
        reachable = bfs_backward(SIG_DAO, callers_map, max_depth=1)
        assert SIG_SVC in reachable
        assert SIG_MAIN not in reachable

    def test_stops_at_from_sig(self):
        from rev_calltree import bfs_backward

        callers_map = {SIG_SVC: [SIG_MAIN], SIG_DAO: [SIG_SVC]}
        reachable = bfs_backward(SIG_DAO, callers_map, max_depth=10, stop_at=SIG_SVC)
        # stop_at SIG_SVC: svc is included but its callers are not explored
        assert SIG_SVC in reachable
        assert SIG_MAIN not in reachable

    def test_target_not_in_reachable(self):
        from rev_calltree import bfs_backward

        callers_map = {SIG_DAO: [SIG_SVC]}
        reachable = bfs_backward(SIG_DAO, callers_map, max_depth=10)
        assert SIG_DAO not in reachable


class TestEnumerateChains:
    def test_single_chain(self):
        from rev_calltree import enumerate_chains

        # main→svc→dao; target=dao
        reachable = {SIG_MAIN, SIG_SVC}
        chains = enumerate_chains(SIG_DAO, reachable, CALLEES, max_chains=10)
        assert len(chains) == 1
        assert chains[0] == [SIG_MAIN, SIG_SVC, SIG_DAO]

    def test_multiple_entry_points(self):
        from rev_calltree import enumerate_chains

        # Two roots: main and util can both reach dao (add util→dao path)
        callees = {
            SIG_MAIN: [SIG_SVC],
            SIG_SVC: [SIG_DAO],
            SIG_UTIL: [SIG_DAO],
        }
        reachable = {SIG_MAIN, SIG_SVC, SIG_UTIL}
        chains = enumerate_chains(SIG_DAO, reachable, callees, max_chains=10)
        assert len(chains) == 2

    def test_respects_max_chains(self):
        from rev_calltree import enumerate_chains

        callees = {
            SIG_MAIN: [SIG_SVC],
            SIG_SVC: [SIG_DAO],
            SIG_UTIL: [SIG_DAO],
        }
        reachable = {SIG_MAIN, SIG_SVC, SIG_UTIL}
        chains = enumerate_chains(SIG_DAO, reachable, callees, max_chains=1)
        assert len(chains) == 1


class TestBuildFramesGraph:
    def test_nodes_include_target_and_callers(self):
        from rev_calltree import build_frames_graph

        nodes, calls = build_frames_graph(
            [[SIG_MAIN, SIG_SVC, SIG_DAO]], CALLSITES, METHOD_LINES
        )
        assert SIG_MAIN in nodes
        assert SIG_SVC in nodes
        assert SIG_DAO in nodes

    def test_calls_include_edges_with_callsite_lines(self):
        from rev_calltree import build_frames_graph

        nodes, calls = build_frames_graph(
            [[SIG_MAIN, SIG_SVC, SIG_DAO]], CALLSITES, METHOD_LINES
        )
        svc_edge = next(
            c for c in calls if c["from"] == SIG_MAIN and c["to"] == SIG_SVC
        )
        assert svc_edge["callSiteLine"] == 10
        dao_edge = next(c for c in calls if c["from"] == SIG_SVC and c["to"] == SIG_DAO)
        assert dao_edge["callSiteLine"] == 35

    def test_node_has_line_metadata(self):
        from rev_calltree import build_frames_graph

        nodes, calls = build_frames_graph(
            [[SIG_MAIN, SIG_SVC, SIG_DAO]], CALLSITES, METHOD_LINES
        )
        assert nodes[SIG_DAO]["lineStart"] == 50
        assert nodes[SIG_DAO]["lineEnd"] == 70
        assert nodes[SIG_DAO]["sourceLineCount"] == 21

    def test_no_duplicate_nodes(self):
        from rev_calltree import build_frames_graph

        # Two chains sharing SIG_SVC
        chains = [[SIG_MAIN, SIG_SVC, SIG_DAO], [SIG_UTIL, SIG_SVC, SIG_DAO]]
        nodes, calls = build_frames_graph(chains, CALLSITES, METHOD_LINES)
        assert list(nodes.keys()).count(SIG_SVC) == 1

    def test_node_has_node_type_java_method(self):
        from rev_calltree import build_frames_graph

        nodes, calls = build_frames_graph(
            [[SIG_MAIN, SIG_SVC, SIG_DAO]], CALLSITES, METHOD_LINES
        )
        assert nodes[SIG_MAIN]["node_type"] == "java_method"
        assert nodes[SIG_DAO]["node_type"] == "java_method"

    def test_edge_has_edge_info(self):
        from rev_calltree import build_frames_graph

        nodes, calls = build_frames_graph(
            [[SIG_MAIN, SIG_SVC, SIG_DAO]], CALLSITES, METHOD_LINES
        )
        for edge in calls:
            assert edge["edge_info"] == {}
