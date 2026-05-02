"""Tests for ftrace_semantic: pure-function passes for semantic graph building."""

from copy import deepcopy

from ftrace_semantic import (
    _accumulate_merged,
    _format_call,
    assign_clusters_pass,
    assign_trap_clusters,
    blocks_for_cluster,
    build_semantic_graph_pass,
    classify_node_kind,
    make_node_label,
    merge_block_stmts,
    merge_source_trace,
    merge_stmts_pass,
)
from ftrace_types import (
    ClusterRole,
    MergedStmt,
    NodeCounter,
    NodeKind,
    RawStmt,
    RawTrap,
    SourceTraceEntry,
)

# --- merge_block_stmts ---


class TestMergeBlockStmts:
    def test_empty_stmts(self):
        assert merge_block_stmts([]) == []

    def test_single_stmt(self):
        stmts: list[RawStmt] = [{"line": 10, "call": "foo.bar"}]
        result = merge_block_stmts(stmts)
        assert len(result) == 1
        assert result[0]["line"] == 10
        assert result[0]["calls"] == ["foo.bar"]

    def test_merges_same_line(self):
        stmts: list[RawStmt] = [
            {"line": 10, "call": "a.b"},
            {"line": 10, "assign": "x"},
        ]
        result = merge_block_stmts(stmts)
        assert len(result) == 1
        assert result[0]["calls"] == ["a.b"]
        assert result[0]["assigns"] == ["x"]

    def test_different_lines_sorted(self):
        stmts: list[RawStmt] = [
            {"line": 20, "assign": "y"},
            {"line": 10, "call": "a.b"},
        ]
        result = merge_block_stmts(stmts)
        assert len(result) == 2
        assert result[0]["line"] == 10
        assert result[1]["line"] == 20

    def test_negative_line_skipped(self):
        stmts: list[RawStmt] = [{"line": -1}, {"line": 10, "assign": "x"}]
        result = merge_block_stmts(stmts)
        assert len(result) == 1
        assert result[0]["line"] == 10

    def test_branch_merged(self):
        stmts: list[RawStmt] = [{"line": 5, "branch": "x > 0"}]
        result = merge_block_stmts(stmts)
        assert result[0]["branches"] == ["x > 0"]

    def test_does_not_mutate_input(self):
        stmts: list[RawStmt] = [{"line": 10, "call": "foo"}]
        stmts_copy = deepcopy(stmts)
        merge_block_stmts(stmts)
        assert stmts == stmts_copy


# --- merge_source_trace ---


class TestMergeSourceTrace:
    def test_empty(self):
        assert merge_source_trace([]) == []

    def test_single_entry(self):
        entries: list[SourceTraceEntry] = [{"line": 10, "calls": ["a.b"]}]
        result = merge_source_trace(entries)
        assert len(result) == 1
        assert result[0]["calls"] == ["a.b"]

    def test_deduplicates_calls(self):
        entries: list[SourceTraceEntry] = [
            {"line": 10, "calls": ["a.b"]},
            {"line": 10, "calls": ["a.b", "c.d"]},
        ]
        result = merge_source_trace(entries)
        assert len(result) == 1
        assert "a.b" in result[0]["calls"]
        assert "c.d" in result[0]["calls"]
        assert result[0]["calls"].count("a.b") == 1

    def test_branch_merged(self):
        entries: list[SourceTraceEntry] = [{"line": 10, "branch": "x > 0"}]
        result = merge_source_trace(entries)
        assert result[0]["branches"] == ["x > 0"]


# --- _accumulate_merged ---


class TestAccumulateMerged:
    def test_new_line(self):
        result = _accumulate_merged({}, 10, ["foo"], [], [])
        assert 10 in result
        assert result[10]["calls"] == ["foo"]

    def test_merges_into_existing(self):
        acc: dict[int, MergedStmt] = {
            10: {"line": 10, "calls": ["a"], "branches": [], "assigns": []}
        }
        result = _accumulate_merged(acc, 10, ["b"], [], ["x"])
        assert result[10]["calls"] == ["a", "b"]
        assert result[10]["assigns"] == ["x"]

    def test_negative_line_returns_unchanged(self):
        acc: dict[int, MergedStmt] = {}
        result = _accumulate_merged(acc, -1, ["foo"], [], [])
        assert result == {}


# --- assign_trap_clusters ---


class TestAssignTrapClusters:
    def test_empty_traps(self):
        assert assign_trap_clusters([]) == {}

    def test_single_trap(self):
        traps: list[RawTrap] = [
            {
                "handler": "b2",
                "type": "java.io.IOException",
                "coveredBlocks": ["b0", "b1"],
                "handlerBlocks": ["b2", "b3"],
            }
        ]
        result = assign_trap_clusters(traps)
        assert result["b0"]["kind"] == ClusterRole.TRY
        assert result["b0"]["trapIndex"] == 0
        assert result["b2"]["kind"] == ClusterRole.HANDLER
        assert result["b2"]["trapIndex"] == 0

    def test_handler_wins_over_covered(self):
        traps: list[RawTrap] = [
            {
                "handler": "b2",
                "type": "Exception",
                "coveredBlocks": ["b0", "b2"],
                "handlerBlocks": ["b2"],
            }
        ]
        result = assign_trap_clusters(traps)
        assert result["b2"]["kind"] == ClusterRole.HANDLER


# --- blocks_for_cluster ---


class TestBlocksForCluster:
    def test_filters_by_kind_and_index(self):
        assignment = {
            "b0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "b1": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "b2": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            "b3": {"kind": ClusterRole.TRY, "trapIndex": 1},
        }
        result = blocks_for_cluster(assignment, ClusterRole.TRY, 0)
        assert result == ["b0", "b1"]

    def test_empty_assignment(self):
        assert blocks_for_cluster({}, ClusterRole.TRY, 0) == []


# --- make_node_label ---


class TestMakeNodeLabel:
    def test_plain_stmt(self):
        entry: MergedStmt = {"line": 10, "calls": [], "branches": [], "assigns": ["x"]}
        result = make_node_label(entry)
        assert result == ["L10", "x"]

    def test_call_suppresses_assigns(self):
        entry: MergedStmt = {
            "line": 15,
            "calls": ["com.example.Svc.run"],
            "branches": [],
            "assigns": ["y"],
        }
        result = make_node_label(entry)
        assert "L15" in result
        assert "Svc.run" in result
        assert "y" not in result

    def test_empty_entry(self):
        entry: MergedStmt = {"line": 1, "calls": [], "branches": [], "assigns": []}
        assert make_node_label(entry) == ["L1"]


# --- _format_call ---


class TestFormatCall:
    def test_fqcn(self):
        assert _format_call("com.example.Svc.run") == "Svc.run"

    def test_no_package(self):
        assert _format_call("run") == "run"


# --- classify_node_kind ---


class TestClassifyNodeKind:
    def test_branch(self):
        entry: MergedStmt = {
            "line": 10,
            "calls": [],
            "branches": ["x > 0"],
            "assigns": [],
        }
        assert classify_node_kind(entry) == NodeKind.BRANCH

    def test_call(self):
        entry: MergedStmt = {
            "line": 10,
            "calls": ["foo"],
            "branches": [],
            "assigns": [],
        }
        assert classify_node_kind(entry) == NodeKind.CALL

    def test_assign(self):
        entry: MergedStmt = {
            "line": 10,
            "calls": [],
            "branches": [],
            "assigns": ["x"],
        }
        assert classify_node_kind(entry) == NodeKind.ASSIGN

    def test_plain(self):
        entry: MergedStmt = {"line": 10, "calls": [], "branches": [], "assigns": []}
        assert classify_node_kind(entry) == NodeKind.PLAIN


# --- merge_stmts_pass ---


class TestMergeStmtsPass:
    def test_leaf_node_passthrough(self):
        tree = {"class": "Foo", "method": "bar", "ref": True}
        result = merge_stmts_pass(tree)
        assert result.get("ref") is True
        assert (
            "mergedStmts" not in result.get("blocks", [{}])[0]
            if "blocks" in result
            else True
        )

    def test_blocks_get_merged_stmts(self):
        tree = {
            "class": "Foo",
            "method": "bar",
            "blocks": [
                {
                    "id": "b0",
                    "stmts": [{"line": 10, "call": "a.b"}, {"line": 10, "assign": "x"}],
                }
            ],
        }
        result = merge_stmts_pass(tree)
        merged = result["blocks"][0]["mergedStmts"]
        assert len(merged) == 1
        assert merged[0]["calls"] == ["a.b"]

    def test_does_not_mutate_input(self):
        tree = {
            "class": "Foo",
            "method": "bar",
            "blocks": [{"id": "b0", "stmts": [{"line": 10}]}],
        }
        tree_copy = deepcopy(tree)
        merge_stmts_pass(tree)
        assert tree == tree_copy


# --- assign_clusters_pass ---


class TestAssignClustersPass:
    def test_adds_cluster_assignment(self):
        tree = {
            "class": "Foo",
            "method": "bar",
            "traps": [
                {
                    "handler": "b2",
                    "type": "Exception",
                    "coveredBlocks": ["b0"],
                    "handlerBlocks": ["b2"],
                }
            ],
        }
        result = assign_clusters_pass(tree)
        assignment = result.get("metadata", {}).get("clusterAssignment", {})
        assert "b0" in assignment
        assert assignment["b0"]["kind"] == ClusterRole.TRY


# --- build_semantic_graph_pass ---


class TestBuildSemanticGraphPass:
    def test_leaf_passthrough(self):
        tree = {"class": "Foo", "method": "bar", "ref": True}
        result, counter = build_semantic_graph_pass(tree)
        assert result.get("ref") is True
        assert counter.value == 0

    def test_source_trace_method(self):
        tree = {
            "class": "Foo",
            "method": "bar",
            "sourceTrace": [{"line": 10, "calls": ["a.b"]}, {"line": 11}],
            "metadata": {},
        }
        enriched = merge_stmts_pass(tree)
        result, counter = build_semantic_graph_pass(enriched)
        assert len(result.get("nodes", [])) == 2
        assert len(result.get("edges", [])) == 1
        assert result.get("entryNodeId") == "n0"

    def test_blocks_method(self):
        tree = {
            "class": "Foo",
            "method": "bar",
            "blocks": [
                {"id": "b0", "stmts": [{"line": 10, "assign": "x"}]},
                {"id": "b1", "stmts": [{"line": 11, "assign": "y"}]},
            ],
            "edges": [{"fromBlock": "b0", "toBlock": "b1"}],
            "traps": [],
            "metadata": {},
        }
        enriched = merge_stmts_pass(tree)
        result, counter = build_semantic_graph_pass(enriched)
        assert len(result.get("nodes", [])) == 2
        assert len(result.get("edges", [])) == 1

    def test_counter_threading(self):
        tree = {
            "class": "Foo",
            "method": "bar",
            "sourceTrace": [{"line": 10}],
            "metadata": {},
        }
        enriched = merge_stmts_pass(tree)
        result, counter = build_semantic_graph_pass(enriched, NodeCounter(100))
        assert result["nodes"][0]["id"] == "n100"
        assert counter.value == 101
