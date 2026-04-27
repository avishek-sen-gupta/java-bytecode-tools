"""Tests for pass 4: build_semantic_graph."""

from ftrace_types import (
    SemanticNode,
    SemanticEdge,
    SemanticCluster,
    ExceptionEdge,
    NodeKind,
    ClusterRole,
)


class TestResolveInputs:
    def test_extracts_all_fields(self):
        from ftrace_semantic import _resolve_inputs

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0", "stmts": [], "mergedStmts": []}],
            "edges": [{"fromBlock": "B0", "toBlock": "B1"}],
            "traps": [
                {
                    "type": "Ex",
                    "handler": "B1",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B1"],
                }
            ],
        }
        metadata = {
            "clusterAssignment": {"B0": {"kind": "try", "trapIndex": 0}},
            "blockAliases": {"B2": "B0"},
        }
        result = _resolve_inputs(tree, metadata)
        assert result["blocks"] == tree["blocks"]
        assert result["edges"] == tree["edges"]
        assert result["traps"] == tree["traps"]
        assert result["cluster_assignment"] == metadata["clusterAssignment"]
        assert result["block_aliases"] == metadata["blockAliases"]

    def test_defaults_when_fields_missing(self):
        from ftrace_semantic import _resolve_inputs

        result = _resolve_inputs({"class": "Svc"}, {})
        assert result["blocks"] == []
        assert result["edges"] == []
        assert result["traps"] == []
        assert result["cluster_assignment"] == {}
        assert result["block_aliases"] == {}


def _make_enriched_method(
    blocks, traps, cluster_assignment, block_aliases=(), children=(), edges=()
):
    """Build a method node with all intermediate fields from passes 1-3."""
    return {
        "class": "com.example.Svc",
        "method": "handle",
        "methodSignature": "<com.example.Svc: void handle()>",
        "lineStart": 1,
        "lineEnd": 20,
        "sourceLineCount": 20,
        "blocks": blocks,
        "edges": list(edges) if edges else [],
        "traps": traps,
        "metadata": {
            "clusterAssignment": cluster_assignment,
            "blockAliases": dict(block_aliases) if block_aliases else {},
        },
        "children": list(children) if children else [],
    }


class TestMakeNodeLabel:
    def test_plain_line(self):
        from ftrace_semantic import make_node_label

        entry = {"line": 6, "calls": [], "branches": [], "assigns": []}
        assert make_node_label(entry) == ["L6"]

    def test_line_with_calls(self):
        from ftrace_semantic import make_node_label

        entry = {
            "line": 9,
            "calls": ["java.lang.RuntimeException.<init>"],
            "branches": [],
            "assigns": [],
        }
        label = make_node_label(entry)
        assert label == ["L9", "RuntimeException.<init>"]

    def test_line_with_assigns_no_calls(self):
        from ftrace_semantic import make_node_label

        entry = {"line": 7, "calls": [], "branches": [], "assigns": ["x = 5"]}
        assert make_node_label(entry) == ["L7", "x = 5"]

    def test_assigns_suppressed_when_calls_present(self):
        from ftrace_semantic import make_node_label

        entry = {"line": 7, "calls": ["Foo.bar"], "branches": [], "assigns": ["x = 5"]}
        assert make_node_label(entry) == ["L7", "Foo.bar"]


class TestClassifyNodeKind:
    def test_branch(self):
        from ftrace_semantic import classify_node_kind

        assert (
            classify_node_kind(
                {"line": 6, "calls": [], "branches": ["i <= 0"], "assigns": []}
            )
            == NodeKind.BRANCH
        )

    def test_call(self):
        from ftrace_semantic import classify_node_kind

        assert (
            classify_node_kind(
                {"line": 9, "calls": ["Foo.bar"], "branches": [], "assigns": []}
            )
            == NodeKind.CALL
        )

    def test_assign(self):
        from ftrace_semantic import classify_node_kind

        assert (
            classify_node_kind(
                {"line": 7, "calls": [], "branches": [], "assigns": ["x = 5"]}
            )
            == NodeKind.ASSIGN
        )

    def test_plain(self):
        from ftrace_semantic import classify_node_kind

        assert (
            classify_node_kind({"line": 5, "calls": [], "branches": [], "assigns": []})
            == NodeKind.PLAIN
        )


class TestBuildNodes:
    def test_single_block_single_stmt(self):
        from ftrace_semantic import _build_nodes

        blocks = [
            {
                "id": "B0",
                "stmts": [],
                "mergedStmts": [
                    {"line": 5, "calls": [], "branches": [], "assigns": []}
                ],
            }
        ]
        result = _build_nodes(blocks, {}, 0)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "n0"
        assert result["nodes"][0]["kind"] == NodeKind.PLAIN
        assert result["block_first"] == {"B0": "n0"}
        assert result["block_last"] == {"B0": "n0"}
        assert result["bid_to_nids"] == {"B0": ["n0"]}
        assert result["node_counter"] == 1

    def test_aliased_block_shares_canonical_nodes(self):
        from ftrace_semantic import _build_nodes

        blocks = [
            {
                "id": "B0",
                "stmts": [],
                "mergedStmts": [
                    {"line": 5, "calls": [], "branches": [], "assigns": []}
                ],
            },
            {
                "id": "B1",
                "stmts": [],
                "mergedStmts": [
                    {"line": 5, "calls": [], "branches": [], "assigns": []}
                ],
            },
        ]
        result = _build_nodes(blocks, {"B1": "B0"}, 0)
        assert len(result["nodes"]) == 1
        assert result["block_first"]["B1"] == result["block_first"]["B0"]
        assert result["block_last"]["B1"] == result["block_last"]["B0"]

    def test_empty_merged_stmts_produces_placeholder(self):
        from ftrace_semantic import _build_nodes

        blocks = [{"id": "B0", "stmts": [], "mergedStmts": []}]
        result = _build_nodes(blocks, {}, 0)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["kind"] == NodeKind.PLAIN
        assert result["nodes"][0]["label"] == ["B0"]
        assert result["nodes"][0]["lines"] == []

    def test_branch_block_last_node_is_branch_kind(self):
        from ftrace_semantic import _build_nodes

        blocks = [
            {
                "id": "B0",
                "stmts": [],
                "mergedStmts": [
                    {"line": 6, "calls": [], "branches": ["i <= 0"], "assigns": []},
                ],
                "branchCondition": "i <= 0",
            }
        ]
        result = _build_nodes(blocks, {}, 0)
        assert result["nodes"][0]["kind"] == NodeKind.BRANCH
        assert "i <= 0" in result["nodes"][0]["label"]

    def test_next_id_offsets_node_ids(self):
        from ftrace_semantic import _build_nodes

        blocks = [
            {
                "id": "B0",
                "stmts": [],
                "mergedStmts": [
                    {"line": 5, "calls": [], "branches": [], "assigns": []}
                ],
            }
        ]
        result = _build_nodes(blocks, {}, 42)
        assert result["nodes"][0]["id"] == "n42"
        assert result["node_counter"] == 43

    def test_multi_stmt_block_produces_sequential_nodes(self):
        from ftrace_semantic import _build_nodes

        blocks = [
            {
                "id": "B0",
                "stmts": [],
                "mergedStmts": [
                    {"line": 5, "calls": [], "branches": [], "assigns": []},
                    {"line": 6, "calls": ["Foo.bar"], "branches": [], "assigns": []},
                ],
            }
        ]
        result = _build_nodes(blocks, {}, 0)
        assert len(result["nodes"]) == 2
        assert result["block_first"]["B0"] == "n0"
        assert result["block_last"]["B0"] == "n1"
        assert result["bid_to_nids"]["B0"] == ["n0", "n1"]


class TestBuildEdges:
    def test_intra_block_sequential_edges(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[],
            block_first={"B0": "n0"},
            block_last={"B0": "n1"},
            bid_to_nids={"B0": ["n0", "n1"]},
            block_aliases={},
        )
        assert result["edges"] == [{"from": "n0", "to": "n1"}]

    def test_inter_block_unconditional_edge(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[{"fromBlock": "B0", "toBlock": "B1"}],
            block_first={"B0": "n0", "B1": "n1"},
            block_last={"B0": "n0", "B1": "n1"},
            bid_to_nids={"B0": ["n0"], "B1": ["n1"]},
            block_aliases={},
        )
        unconditional = [e for e in result["edges"] if "branch" not in e]
        assert {"from": "n0", "to": "n1"} in unconditional

    def test_branch_edges_with_labels(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[
                {"fromBlock": "B0", "toBlock": "B1", "label": "T"},
                {"fromBlock": "B0", "toBlock": "B2", "label": "F"},
            ],
            block_first={"B0": "n0", "B1": "n1", "B2": "n2"},
            block_last={"B0": "n0", "B1": "n1", "B2": "n2"},
            bid_to_nids={"B0": ["n0"], "B1": ["n1"], "B2": ["n2"]},
            block_aliases={},
        )
        branch_edges = [e for e in result["edges"] if "branch" in e]
        labels = {e["branch"] for e in branch_edges}
        assert labels == {"T", "F"}

    def test_self_loop_suppressed(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[{"fromBlock": "B0", "toBlock": "B1"}],
            block_first={"B0": "n0", "B1": "n0"},
            block_last={"B0": "n0", "B1": "n0"},
            bid_to_nids={"B0": ["n0"], "B1": ["n0"]},
            block_aliases={"B1": "B0"},
        )
        inter_edges = [
            e for e in result["edges"] if e.get("from") != e.get("to") or "branch" in e
        ]
        self_loops = [e for e in result["edges"] if e["from"] == e["to"]]
        assert self_loops == []

    def test_duplicate_edges_deduplicated(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[
                {"fromBlock": "B0", "toBlock": "B1"},
                {"fromBlock": "B0", "toBlock": "B1"},
            ],
            block_first={"B0": "n0", "B1": "n1"},
            block_last={"B0": "n0", "B1": "n1"},
            bid_to_nids={"B0": ["n0"], "B1": ["n1"]},
            block_aliases={},
        )
        unconditional = [e for e in result["edges"] if "branch" not in e]
        assert len(unconditional) == 1

    def test_branch_both_targets_same_keeps_both_labels(self):
        """When T and F edges target the same block, both labels should be kept."""
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[
                {"fromBlock": "B0", "toBlock": "B1", "label": "T"},
                {"fromBlock": "B0", "toBlock": "B1", "label": "F"},
            ],
            block_first={"B0": "n0", "B1": "n1"},
            block_last={"B0": "n0", "B1": "n1"},
            bid_to_nids={"B0": ["n0"], "B1": ["n1"]},
            block_aliases={},
        )
        branch_edges = [e for e in result["edges"] if "branch" in e]
        assert len(branch_edges) == 2
        labels = {e["branch"] for e in branch_edges}
        assert labels == {"T", "F"}


class TestBuildClusters:
    def test_single_trap_produces_try_and_handler_clusters(self):
        from ftrace_semantic import _build_clusters

        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B3",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B3"],
            }
        ]
        cluster_assignment = {
            "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
        }
        bid_to_nids = {"B0": ["n0"], "B3": ["n1"]}
        block_first = {"B0": "n0", "B3": "n1"}

        result = _build_clusters(traps, cluster_assignment, bid_to_nids, block_first)
        assert len(result["clusters"]) == 2

        try_cluster = [c for c in result["clusters"] if c["role"] == ClusterRole.TRY][0]
        handler_cluster = [
            c for c in result["clusters"] if c["role"] == ClusterRole.HANDLER
        ][0]
        assert try_cluster["trapType"] == "RuntimeException"
        assert try_cluster["nodeIds"] == ["n0"]
        assert handler_cluster["trapType"] == "RuntimeException"
        assert handler_cluster["nodeIds"] == ["n1"]
        assert handler_cluster["entryNodeId"] == "n1"

    def test_exception_edge_emitted(self):
        from ftrace_semantic import _build_clusters

        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B3",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B3"],
            }
        ]
        cluster_assignment = {
            "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
        }
        bid_to_nids = {"B0": ["n0"], "B3": ["n1"]}
        block_first = {"B0": "n0", "B3": "n1"}

        result = _build_clusters(traps, cluster_assignment, bid_to_nids, block_first)
        assert len(result["exception_edges"]) == 1
        ee = result["exception_edges"][0]
        assert ee["from"] == "n0"
        assert ee["to"] == "n1"
        assert ee["trapType"] == "RuntimeException"
        assert ee["fromCluster"] == 0
        assert ee["toCluster"] == 1

    def test_no_traps_produces_empty(self):
        from ftrace_semantic import _build_clusters

        result = _build_clusters([], {}, {}, {})
        assert result["clusters"] == []
        assert result["exception_edges"] == []


class TestBuildSemanticGraphPass:
    def test_simple_linear_chain(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                },
                {
                    "id": "B1",
                    "stmts": [],
                    "mergedStmts": [
                        {
                            "line": 10,
                            "calls": ["Foo.bar"],
                            "branches": [],
                            "assigns": [],
                        }
                    ],
                },
            ],
            traps=[],
            cluster_assignment={},
            edges=[{"fromBlock": "B0", "toBlock": "B1"}],
        )
        result = build_semantic_graph_pass(tree)

        assert "nodes" in result
        assert "edges" in result
        assert "clusters" in result
        assert "blocks" not in result
        assert "traps" not in result
        assert (
            "mergedStmts" not in result.get("blocks", [{}])[0]
            if "blocks" in result
            else True
        )

        assert len(result["nodes"]) == 2
        assert result["nodes"][0]["kind"] == NodeKind.PLAIN
        assert result["nodes"][1]["kind"] == NodeKind.CALL

        assert len(result["edges"]) == 1
        assert result["edges"][0]["from"] == result["nodes"][0]["id"]
        assert result["edges"][0]["to"] == result["nodes"][1]["id"]

    def test_branch_edges(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 6, "calls": [], "branches": ["i <= 0"], "assigns": []}
                    ],
                    "branchCondition": "i <= 0",
                },
                {
                    "id": "B1",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 7, "calls": [], "branches": [], "assigns": []}
                    ],
                },
                {
                    "id": "B2",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 9, "calls": [], "branches": [], "assigns": []}
                    ],
                },
            ],
            traps=[],
            cluster_assignment={},
            edges=[
                {"fromBlock": "B0", "toBlock": "B1", "label": "T"},
                {"fromBlock": "B0", "toBlock": "B2", "label": "F"},
            ],
        )
        result = build_semantic_graph_pass(tree)

        branch_edges = [e for e in result["edges"] if "branch" in e]
        assert len(branch_edges) == 2
        labels = {e["branch"] for e in branch_edges}
        assert labels == {"T", "F"}

    def test_self_loops_suppressed(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 9, "calls": [], "branches": [], "assigns": []}
                    ],
                },
                {
                    "id": "B1",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 9, "calls": [], "branches": [], "assigns": []}
                    ],
                },
            ],
            traps=[],
            cluster_assignment={
                "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
                "B1": {"kind": ClusterRole.TRY, "trapIndex": 0},
            },
            block_aliases={"B1": "B0"},
            edges=[{"fromBlock": "B0", "toBlock": "B1"}],
        )
        result = build_semantic_graph_pass(tree)

        self_loops = [e for e in result["edges"] if e["from"] == e["to"]]
        assert self_loops == []

    def test_clusters_emitted(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                },
                {
                    "id": "B3",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 11, "calls": [], "branches": [], "assigns": []}
                    ],
                },
            ],
            traps=[
                {
                    "type": "java.lang.RuntimeException",
                    "handler": "B3",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B3"],
                },
            ],
            cluster_assignment={
                "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
                "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            },
        )
        result = build_semantic_graph_pass(tree)

        assert len(result["clusters"]) == 2
        try_cluster = [c for c in result["clusters"] if c["role"] == ClusterRole.TRY][0]
        handler_cluster = [
            c for c in result["clusters"] if c["role"] == ClusterRole.HANDLER
        ][0]
        assert try_cluster["trapType"] == "RuntimeException"
        assert len(try_cluster["nodeIds"]) == 1
        assert handler_cluster["entryNodeId"] == handler_cluster["nodeIds"][0]

    def test_exception_edges_emitted(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                },
                {
                    "id": "B3",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 11, "calls": [], "branches": [], "assigns": []}
                    ],
                },
            ],
            traps=[
                {
                    "type": "java.lang.RuntimeException",
                    "handler": "B3",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B3"],
                },
            ],
            cluster_assignment={
                "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
                "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            },
        )
        result = build_semantic_graph_pass(tree)

        assert len(result["exceptionEdges"]) == 1
        ee = result["exceptionEdges"][0]
        assert ee["trapType"] == "RuntimeException"

    def test_raw_fields_removed(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                },
            ],
            traps=[],
            cluster_assignment={},
        )
        result = build_semantic_graph_pass(tree)

        for field in (
            "blocks",
            "traps",
            "metadata",
            "sourceTrace",
        ):
            assert field not in result, f"{field} should be removed"

    def test_preserves_tree_metadata(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                },
            ],
            traps=[],
            cluster_assignment={},
        )
        result = build_semantic_graph_pass(tree)

        assert result["class"] == "com.example.Svc"
        assert result["method"] == "handle"
        assert result["lineStart"] == 1
        assert result["lineEnd"] == 20

    def test_leaf_ref_node(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = {
            "class": "com.example.Svc",
            "method": "run",
            "methodSignature": "sig",
            "ref": True,
        }
        result = build_semantic_graph_pass(tree)
        assert result.get("ref") is True
        assert "nodes" not in result

    def test_leaf_cycle_node(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = {
            "class": "com.example.Svc",
            "method": "run",
            "methodSignature": "sig",
            "cycle": True,
        }
        result = build_semantic_graph_pass(tree)
        assert result.get("cycle") is True

    def test_leaf_filtered_node(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = {
            "class": "com.example.Svc",
            "method": "run",
            "methodSignature": "sig",
            "filtered": True,
        }
        result = build_semantic_graph_pass(tree)
        assert result.get("filtered") is True

    def test_does_not_mutate_input(self):
        from ftrace_semantic import build_semantic_graph_pass
        import copy

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                },
            ],
            traps=[],
            cluster_assignment={},
        )
        original = copy.deepcopy(tree)
        build_semantic_graph_pass(tree)
        assert tree == original


class TestSourceTraceFallback:
    def test_empty_source_trace_produces_empty_graph(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = {
            "class": "com.example.Svc",
            "method": "run",
            "methodSignature": "sig",
            "lineStart": 5,
            "lineEnd": 10,
            "sourceLineCount": 6,
            "metadata": {"mergedSourceTrace": []},
            "children": [],
        }
        result = build_semantic_graph_pass(tree)

        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["clusters"] == []
        assert result["exceptionEdges"] == []
        assert "entryNodeId" not in result

    def test_source_trace_produces_linear_nodes(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = {
            "class": "com.example.Svc",
            "method": "run",
            "methodSignature": "sig",
            "lineStart": 5,
            "lineEnd": 10,
            "sourceLineCount": 6,
            "metadata": {
                "mergedSourceTrace": [
                    {"line": 5, "calls": [], "branches": [], "assigns": []},
                    {"line": 10, "calls": ["Foo.bar"], "branches": [], "assigns": []},
                ],
            },
            "children": [],
        }
        result = build_semantic_graph_pass(tree)

        assert len(result["nodes"]) == 2
        assert result["nodes"][0]["kind"] == NodeKind.PLAIN
        assert result["nodes"][1]["kind"] == NodeKind.CALL
        assert len(result["edges"]) == 1
        assert result["edges"][0]["from"] == result["nodes"][0]["id"]
        # Edge "to" field connects to next node
        assert result["edges"][0]["to"] == result["nodes"][1]["id"]
        # entryNodeId equals first node's id
        assert result["entryNodeId"] == result["nodes"][0]["id"]
        # clusters is empty list
        assert result["clusters"] == []
        # exceptionEdges is empty list
        assert result["exceptionEdges"] == []
        # sourceTrace and mergedSourceTrace are NOT in result
        assert "sourceTrace" not in result
        assert "metadata" not in result


class TestTransform:
    def test_transform_runs_all_passes(self):
        from ftrace_semantic import transform

        tree = {
            "class": "Svc",
            "method": "run",
            "methodSignature": "<Svc: void run()>",
            "lineStart": 1,
            "lineEnd": 10,
            "sourceLineCount": 10,
            "blocks": [
                {"id": "B0", "stmts": [{"line": 5}]},
                {"id": "B1", "stmts": [{"line": 10, "call": "Foo.bar"}]},
            ],
            "edges": [{"fromBlock": "B0", "toBlock": "B1"}],
            "traps": [],
            "children": [],
        }
        result, violations = transform(tree)

        # Should have semantic fields
        assert "nodes" in result
        assert "edges" in result
        assert "clusters" in result
        assert "exceptionEdges" in result

        # Should not have raw fields
        assert "blocks" not in result
        assert "traps" not in result

        # Clean graph should have no violations
        assert violations == []

    def test_transform_leaf_node(self):
        from ftrace_semantic import transform

        tree = {"class": "Svc", "method": "run", "methodSignature": "sig", "ref": True}
        result, violations = transform(tree)
        assert result.get("ref") is True
        assert "nodes" not in result
        assert violations == []


class TestBuildFromSourceTrace:
    def test_linear_nodes_and_sequential_edges(self):
        from ftrace_semantic import _build_from_source_trace

        merged = [
            {"line": 5, "calls": [], "branches": [], "assigns": []},
            {"line": 8, "calls": ["Foo.bar"], "branches": [], "assigns": []},
            {"line": 12, "calls": [], "branches": [], "assigns": []},
        ]
        result = _build_from_source_trace(merged, 0)
        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2
        assert result["edges"][0]["from"] == result["nodes"][0]["id"]
        assert result["edges"][0]["to"] == result["nodes"][1]["id"]
        assert result["edges"][1]["from"] == result["nodes"][1]["id"]
        assert result["edges"][1]["to"] == result["nodes"][2]["id"]

    def test_node_kinds_and_labels(self):
        from ftrace_semantic import _build_from_source_trace

        merged = [
            {"line": 5, "calls": [], "branches": [], "assigns": []},
            {"line": 8, "calls": ["Foo.bar"], "branches": [], "assigns": []},
        ]
        result = _build_from_source_trace(merged, 0)
        assert result["nodes"][0]["kind"] == NodeKind.PLAIN
        assert result["nodes"][1]["kind"] == NodeKind.CALL
        assert result["nodes"][0]["lines"] == [5]
        assert result["nodes"][1]["lines"] == [8]

    def test_node_ids_respect_next_id(self):
        from ftrace_semantic import _build_from_source_trace

        merged = [{"line": 5, "calls": [], "branches": [], "assigns": []}]
        result = _build_from_source_trace(merged, 42)
        assert result["nodes"][0]["id"] == "n42"
        assert result["node_counter"] == 43

    def test_empty_source_trace(self):
        from ftrace_semantic import _build_from_source_trace

        result = _build_from_source_trace([], 0)
        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["clusters"] == []
        assert result["exception_edges"] == []

    def test_does_not_mutate_input(self):
        import copy

        from ftrace_semantic import _build_from_source_trace

        merged = [
            {"line": 5, "calls": [], "branches": [], "assigns": []},
            {"line": 10, "calls": ["Foo.bar"], "branches": [], "assigns": []},
        ]
        original = copy.deepcopy(merged)
        _build_from_source_trace(merged, 0)
        assert merged == original


class TestBuildFromBlocks:
    def test_produces_nodes_and_edges(self):
        from ftrace_semantic import _build_from_blocks

        tree = {
            "blocks": [
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                },
                {
                    "id": "B1",
                    "stmts": [],
                    "mergedStmts": [
                        {
                            "line": 10,
                            "calls": ["Foo.bar"],
                            "branches": [],
                            "assigns": [],
                        }
                    ],
                },
            ],
            "edges": [{"fromBlock": "B0", "toBlock": "B1"}],
            "traps": [],
        }
        metadata = {"clusterAssignment": {}, "blockAliases": {}}
        result = _build_from_blocks(tree, metadata, 0)
        assert len(result["nodes"]) == 2
        assert any(
            e["from"] == result["nodes"][0]["id"]
            and e["to"] == result["nodes"][1]["id"]
            for e in result["edges"]
        )

    def test_includes_clusters_when_traps_present(self):
        from ftrace_semantic import _build_from_blocks

        tree = {
            "blocks": [
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                },
                {
                    "id": "B1",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 10, "calls": [], "branches": [], "assigns": []}
                    ],
                },
            ],
            "edges": [],
            "traps": [
                {
                    "type": "java.lang.Exception",
                    "handler": "B1",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B1"],
                }
            ],
        }
        metadata = {
            "clusterAssignment": {
                "B0": {"kind": "try", "trapIndex": 0},
                "B1": {"kind": "handler", "trapIndex": 0},
            },
            "blockAliases": {},
        }
        result = _build_from_blocks(tree, metadata, 0)
        assert len(result["clusters"]) >= 1

    def test_returns_correct_node_counter(self):
        from ftrace_semantic import _build_from_blocks

        tree = {
            "blocks": [
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                },
            ],
            "edges": [],
            "traps": [],
        }
        metadata = {"clusterAssignment": {}, "blockAliases": {}}
        result = _build_from_blocks(tree, metadata, 0)
        assert result["node_counter"] >= 1

    def test_does_not_mutate_input(self):
        import copy

        from ftrace_semantic import _build_from_blocks

        tree = {
            "blocks": [
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                },
            ],
            "edges": [],
            "traps": [],
        }
        metadata = {"clusterAssignment": {}, "blockAliases": {}}
        original_tree = copy.deepcopy(tree)
        original_meta = copy.deepcopy(metadata)
        _build_from_blocks(tree, metadata, 0)
        assert tree == original_tree
        assert metadata == original_meta


class TestAssembleResult:
    def test_drops_specified_fields(self):
        from ftrace_semantic import _assemble_result

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0"}],
            "traps": [],
            "metadata": {"stuff": True},
        }
        build_result = {
            "nodes": [],
            "edges": [],
            "clusters": [],
            "exception_edges": [],
            "node_counter": 0,
        }
        result = _assemble_result(
            tree, build_result, frozenset({"blocks", "traps", "metadata"})
        )
        assert "blocks" not in result
        assert "traps" not in result
        assert "metadata" not in result

    def test_preserves_identity_fields(self):
        from ftrace_semantic import _assemble_result

        tree = {
            "class": "Svc",
            "method": "run",
            "methodSignature": "sig",
            "lineStart": 1,
            "lineEnd": 10,
        }
        build_result = {
            "nodes": [],
            "edges": [],
            "clusters": [],
            "exception_edges": [],
            "node_counter": 0,
        }
        result = _assemble_result(tree, build_result, frozenset())
        assert result["method"] == "run"
        assert result["methodSignature"] == "sig"
        assert result["lineStart"] == 1
        assert result["lineEnd"] == 10

    def test_sets_entry_node_id_when_nodes_present(self):
        from ftrace_semantic import _assemble_result

        tree = {"class": "Svc", "method": "run"}
        build_result = {
            "nodes": [
                {"id": "n0", "lines": [5], "kind": NodeKind.PLAIN, "label": ["L5"]},
                {"id": "n1", "lines": [10], "kind": NodeKind.PLAIN, "label": ["L10"]},
            ],
            "edges": [],
            "clusters": [],
            "exception_edges": [],
            "node_counter": 2,
        }
        result = _assemble_result(tree, build_result, frozenset())
        assert result["entryNodeId"] == "n0"

    def test_no_entry_node_id_when_no_nodes(self):
        from ftrace_semantic import _assemble_result

        tree = {"class": "Svc", "method": "run"}
        build_result = {
            "nodes": [],
            "edges": [],
            "clusters": [],
            "exception_edges": [],
            "node_counter": 0,
        }
        result = _assemble_result(tree, build_result, frozenset())
        assert "entryNodeId" not in result

    def test_recurses_children(self):
        from ftrace_semantic import _assemble_result

        child = {
            "class": "Svc",
            "method": "inner",
            "methodSignature": "sig",
            "ref": True,
        }
        tree = {"class": "Svc", "method": "run", "children": [child]}
        build_result = {
            "nodes": [
                {"id": "n0", "lines": [5], "kind": NodeKind.PLAIN, "label": ["L5"]},
            ],
            "edges": [],
            "clusters": [],
            "exception_edges": [],
            "node_counter": 1,
        }
        result = _assemble_result(tree, build_result, frozenset())
        assert "children" in result
        assert len(result["children"]) == 1
        assert result["children"][0]["method"] == "inner"


class TestResolveEdgeTriples:
    def test_resolves_block_ids_to_node_ids(self):
        from ftrace_semantic import _resolve_edge_triples

        raw_edges = [{"fromBlock": "B0", "toBlock": "B1"}]
        result = _resolve_edge_triples(
            raw_edges,
            block_first={"B0": "n0", "B1": "n1"},
            block_last={"B0": "n0", "B1": "n1"},
            aliased_blocks=frozenset(),
        )
        assert len(result) == 1
        assert result[0]["from_nid"] == "n0"
        assert result[0]["to_nid"] == "n1"
        assert result[0]["to_block"] == "B1"

    def test_filters_aliased_block_edges(self):
        from ftrace_semantic import _resolve_edge_triples

        raw_edges = [
            {"fromBlock": "B0", "toBlock": "B1"},
            {"fromBlock": "B2", "toBlock": "B1"},
        ]
        result = _resolve_edge_triples(
            raw_edges,
            block_first={"B0": "n0", "B1": "n1", "B2": "n0"},
            block_last={"B0": "n0", "B1": "n1", "B2": "n0"},
            aliased_blocks=frozenset({"B2"}),
        )
        assert len(result) == 1
        assert result[0]["from_nid"] == "n0"

    def test_filters_missing_node_edges(self):
        from ftrace_semantic import _resolve_edge_triples

        raw_edges = [{"fromBlock": "B0", "toBlock": "B_missing"}]
        result = _resolve_edge_triples(
            raw_edges,
            block_first={"B0": "n0"},
            block_last={"B0": "n0"},
            aliased_blocks=frozenset(),
        )
        assert result == []

    def test_filters_self_loops(self):
        from ftrace_semantic import _resolve_edge_triples

        raw_edges = [{"fromBlock": "B0", "toBlock": "B1"}]
        result = _resolve_edge_triples(
            raw_edges,
            block_first={"B0": "n0", "B1": "n0"},
            block_last={"B0": "n0", "B1": "n0"},
            aliased_blocks=frozenset(),
        )
        assert result == []

    def test_preserves_label(self):
        from ftrace_semantic import _resolve_edge_triples

        raw_edges = [{"fromBlock": "B0", "toBlock": "B1", "label": "T"}]
        result = _resolve_edge_triples(
            raw_edges,
            block_first={"B0": "n0", "B1": "n1"},
            block_last={"B0": "n0", "B1": "n1"},
            aliased_blocks=frozenset(),
        )
        assert result[0]["label"] == "T"

    def test_preserves_edge_order(self):
        from ftrace_semantic import _resolve_edge_triples

        raw_edges = [
            {"fromBlock": "B0", "toBlock": "B1"},
            {"fromBlock": "B0", "toBlock": "B2"},
        ]
        result = _resolve_edge_triples(
            raw_edges,
            block_first={"B0": "n0", "B1": "n1", "B2": "n2"},
            block_last={"B0": "n0", "B1": "n1", "B2": "n2"},
            aliased_blocks=frozenset(),
        )
        assert result[0]["to_nid"] == "n1"
        assert result[1]["to_nid"] == "n2"

    def test_does_not_mutate_input(self):
        import copy

        from ftrace_semantic import _resolve_edge_triples

        raw_edges = [{"fromBlock": "B0", "toBlock": "B1", "label": "T"}]
        original = copy.deepcopy(raw_edges)
        _resolve_edge_triples(
            raw_edges,
            block_first={"B0": "n0", "B1": "n1"},
            block_last={"B0": "n0", "B1": "n1"},
            aliased_blocks=frozenset(),
        )
        assert raw_edges == original


class TestClassifyConvergence:
    def test_single_labeled_edge_kept(self):
        from ftrace_semantic import _classify_convergence

        resolved = [{"from_nid": "n0", "to_nid": "n1", "label": "T", "to_block": "B1"}]
        result = _classify_convergence(resolved)
        assert len(result) == 1
        assert result[0]["from"] == "n0"
        assert result[0]["to"] == "n1"
        assert result[0]["branch"] == "T"

    def test_single_unlabeled_edge_kept(self):
        from ftrace_semantic import _classify_convergence

        resolved = [{"from_nid": "n0", "to_nid": "n1", "label": "", "to_block": "B1"}]
        result = _classify_convergence(resolved)
        assert len(result) == 1
        assert result[0]["from"] == "n0"
        assert result[0]["to"] == "n1"
        assert "branch" not in result[0]

    def test_natural_convergence_keeps_both_labels(self):
        from ftrace_semantic import _classify_convergence

        resolved = [
            {"from_nid": "n0", "to_nid": "n1", "label": "T", "to_block": "B1"},
            {"from_nid": "n0", "to_nid": "n1", "label": "F", "to_block": "B1"},
        ]
        result = _classify_convergence(resolved)
        assert len(result) == 2
        labels = {e["branch"] for e in result}
        assert labels == {"T", "F"}

    def test_aliasing_convergence_collapses_to_unlabeled(self):
        from ftrace_semantic import _classify_convergence

        resolved = [
            {"from_nid": "n0", "to_nid": "n1", "label": "T", "to_block": "B1"},
            {"from_nid": "n0", "to_nid": "n1", "label": "F", "to_block": "B2"},
        ]
        result = _classify_convergence(resolved)
        assert len(result) == 1
        assert result[0]["from"] == "n0"
        assert result[0]["to"] == "n1"
        assert "branch" not in result[0]

    def test_multiple_independent_groups(self):
        from ftrace_semantic import _classify_convergence

        resolved = [
            {"from_nid": "n0", "to_nid": "n1", "label": "T", "to_block": "B1"},
            {"from_nid": "n0", "to_nid": "n2", "label": "F", "to_block": "B2"},
        ]
        result = _classify_convergence(resolved)
        assert len(result) == 2

    def test_does_not_mutate_input(self):
        import copy

        from ftrace_semantic import _classify_convergence

        resolved = [
            {"from_nid": "n0", "to_nid": "n1", "label": "T", "to_block": "B1"},
        ]
        original = copy.deepcopy(resolved)
        _classify_convergence(resolved)
        assert resolved == original


class TestSuppressReverseEdges:
    def test_suppresses_reverse_at_shared_node(self):
        from ftrace_semantic import _suppress_reverse_edges

        edges = [
            {"from": "n0", "to": "n1"},
            {"from": "n1", "to": "n0"},
        ]
        result = _suppress_reverse_edges(edges, shared_nids=frozenset({"n0"}))
        assert len(result) == 1
        assert result[0]["from"] == "n0"

    def test_keeps_reverse_at_non_shared_node(self):
        from ftrace_semantic import _suppress_reverse_edges

        edges = [
            {"from": "n0", "to": "n1"},
            {"from": "n1", "to": "n0"},
        ]
        result = _suppress_reverse_edges(edges, shared_nids=frozenset())
        assert len(result) == 2

    def test_labeled_edges_never_suppressed(self):
        from ftrace_semantic import _suppress_reverse_edges

        edges = [
            {"from": "n0", "to": "n1"},
            {"from": "n1", "to": "n0", "branch": "T"},
        ]
        result = _suppress_reverse_edges(edges, shared_nids=frozenset({"n0"}))
        assert len(result) == 2

    def test_does_not_mutate_input(self):
        import copy

        from ftrace_semantic import _suppress_reverse_edges

        edges = [{"from": "n0", "to": "n1"}, {"from": "n1", "to": "n0"}]
        original = copy.deepcopy(edges)
        _suppress_reverse_edges(edges, shared_nids=frozenset({"n0"}))
        assert edges == original
