"""Tests for pass 4: build_semantic_graph."""

from ftrace_types import (
    SemanticNode,
    SemanticEdge,
    SemanticCluster,
    ExceptionEdge,
    NodeKind,
    NodeCounter,
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
        }
        result = _resolve_inputs(tree, metadata)
        assert result["blocks"] == tree["blocks"]
        assert result["edges"] == tree["edges"]
        assert result["traps"] == tree["traps"]
        assert result["cluster_assignment"] == metadata["clusterAssignment"]

    def test_defaults_when_fields_missing(self):
        from ftrace_semantic import _resolve_inputs

        result = _resolve_inputs({"class": "Svc"}, {})
        assert result["blocks"] == []
        assert result["edges"] == []
        assert result["traps"] == []
        assert result["cluster_assignment"] == {}


def _make_enriched_method(blocks, traps, cluster_assignment, children=(), edges=()):
    """Build a method node with all intermediate fields from passes 1-2."""
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
        result = _build_nodes(blocks, 0)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "n0"
        assert result["nodes"][0]["kind"] == NodeKind.PLAIN
        assert result["block_first"] == {"B0": "n0"}
        assert result["block_last"] == {"B0": "n0"}
        assert result["bid_to_nids"] == {"B0": ["n0"]}
        assert result["node_counter"] == 1

    def test_empty_merged_stmts_produces_placeholder(self):
        from ftrace_semantic import _build_nodes

        blocks = [{"id": "B0", "stmts": [], "mergedStmts": []}]
        result = _build_nodes(blocks, 0)
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
        result = _build_nodes(blocks, 0)
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
        result = _build_nodes(blocks, 42)
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
        result = _build_nodes(blocks, 0)
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
        )
        assert result["edges"] == [{"from": "n0", "to": "n1"}]

    def test_inter_block_unconditional_edge(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[{"fromBlock": "B0", "toBlock": "B1"}],
            block_first={"B0": "n0", "B1": "n1"},
            block_last={"B0": "n0", "B1": "n1"},
            bid_to_nids={"B0": ["n0"], "B1": ["n1"]},
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
        )
        branch_edges = [e for e in result["edges"] if "branch" in e]
        labels = {e["branch"] for e in branch_edges}
        assert labels == {"T", "F"}

    def test_self_loop_suppressed(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[{"fromBlock": "B0", "toBlock": "B0"}],
            block_first={"B0": "n0"},
            block_last={"B0": "n0"},
            bid_to_nids={"B0": ["n0"]},
        )
        self_loops = [e for e in result["edges"] if e.get("from") == e.get("to")]
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
        result, _ = build_semantic_graph_pass(tree)

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
        result, _ = build_semantic_graph_pass(tree)

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
            ],
            traps=[],
            cluster_assignment={},
            edges=[{"fromBlock": "B0", "toBlock": "B0"}],
        )
        result, _ = build_semantic_graph_pass(tree)

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
        result, _ = build_semantic_graph_pass(tree)

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
        result, _ = build_semantic_graph_pass(tree)

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
        result, _ = build_semantic_graph_pass(tree)

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
        result, _ = build_semantic_graph_pass(tree)

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
        result, _ = build_semantic_graph_pass(tree)
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
        result, _ = build_semantic_graph_pass(tree)
        assert result.get("cycle") is True

    def test_leaf_filtered_node(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = {
            "class": "com.example.Svc",
            "method": "run",
            "methodSignature": "sig",
            "filtered": True,
        }
        result, _ = build_semantic_graph_pass(tree)
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
        result, _ = build_semantic_graph_pass(tree)

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
        result, _ = build_semantic_graph_pass(tree)

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

    def test_identical_blocks_produce_separate_nodes(self):
        """Blocks with identical content in the same cluster must produce
        separate nodes. Aliasing was removed because it hides structurally
        distinct control flow."""
        from ftrace_semantic import transform

        tree = {
            "class": "Svc",
            "method": "run",
            "methodSignature": "<Svc: void run()>",
            "lineStart": 1,
            "lineEnd": 20,
            "sourceLineCount": 20,
            "blocks": [
                {
                    "id": "B0",
                    "stmts": [{"line": 5}],
                },
                {
                    "id": "B3",
                    "stmts": [
                        {"line": 14, "call": "PrintStream.println"},
                    ],
                },
                {
                    "id": "B8",
                    "stmts": [
                        {"line": 14, "call": "PrintStream.println"},
                    ],
                },
            ],
            "edges": [
                {"fromBlock": "B0", "toBlock": "B3"},
                {"fromBlock": "B0", "toBlock": "B8"},
            ],
            "traps": [
                {
                    "type": "java.lang.Exception",
                    "handler": "B3",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B3", "B8"],
                }
            ],
            "children": [],
        }
        result, violations = transform(tree)

        # B3 and B8 have identical content but must produce separate nodes
        assert (
            len(result["nodes"]) == 3
        ), f"Expected 3 nodes (B0, B3, B8 each separate), got {len(result['nodes'])}"


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
        assert result["counter"].value == 43

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
        metadata = {"clusterAssignment": {}}
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
        }
        result = _build_from_blocks(tree, metadata, 0)
        assert len(result["clusters"]) >= 1

    def test_returns_correct_counter(self):
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
        metadata = {"clusterAssignment": {}}
        result = _build_from_blocks(tree, metadata, 0)
        assert result["counter"].value >= 1

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
        metadata = {"clusterAssignment": {}}
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
            "counter": NodeCounter(0),
        }
        result, _ = _assemble_result(
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
            "counter": NodeCounter(0),
        }
        result, _ = _assemble_result(tree, build_result, frozenset())
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
            "counter": NodeCounter(2),
        }
        result, _ = _assemble_result(tree, build_result, frozenset())
        assert result["entryNodeId"] == "n0"

    def test_no_entry_node_id_when_no_nodes(self):
        from ftrace_semantic import _assemble_result

        tree = {"class": "Svc", "method": "run"}
        build_result = {
            "nodes": [],
            "edges": [],
            "clusters": [],
            "exception_edges": [],
            "counter": NodeCounter(0),
        }
        result, _ = _assemble_result(tree, build_result, frozenset())
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
            "counter": NodeCounter(1),
        }
        result, _ = _assemble_result(tree, build_result, frozenset())
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
        )
        assert len(result) == 1
        assert result[0]["from_nid"] == "n0"
        assert result[0]["to_nid"] == "n1"
        assert result[0]["to_block"] == "B1"

    def test_filters_missing_node_edges(self):
        from ftrace_semantic import _resolve_edge_triples

        raw_edges = [{"fromBlock": "B0", "toBlock": "B_missing"}]
        result = _resolve_edge_triples(
            raw_edges,
            block_first={"B0": "n0"},
            block_last={"B0": "n0"},
        )
        assert result == []

    def test_filters_self_loops(self):
        from ftrace_semantic import _resolve_edge_triples

        raw_edges = [{"fromBlock": "B0", "toBlock": "B1"}]
        result = _resolve_edge_triples(
            raw_edges,
            block_first={"B0": "n0", "B1": "n0"},
            block_last={"B0": "n0", "B1": "n0"},
        )
        assert result == []

    def test_preserves_label(self):
        from ftrace_semantic import _resolve_edge_triples

        raw_edges = [{"fromBlock": "B0", "toBlock": "B1", "label": "T"}]
        result = _resolve_edge_triples(
            raw_edges,
            block_first={"B0": "n0", "B1": "n1"},
            block_last={"B0": "n0", "B1": "n1"},
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


class TestBuildClusterPair:
    def test_try_cluster_contains_covered_block_nodes(self):
        from ftrace_semantic import _build_cluster_pair

        result = _build_cluster_pair(
            trap={
                "type": "java.lang.Exception",
                "handler": "B3",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B3"],
            },
            trap_index=0,
            cluster_assignment={
                "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
                "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            },
            bid_to_nids={"B0": ["n0", "n1"], "B3": ["n2"]},
            block_first={"B0": "n0", "B3": "n2"},
        )
        assert result["try_cluster"]["nodeIds"] == ["n0", "n1"]
        assert result["try_cluster"]["role"] == ClusterRole.TRY
        assert result["try_cluster"]["trapType"] == "Exception"

    def test_handler_cluster_contains_handler_block_nodes(self):
        from ftrace_semantic import _build_cluster_pair

        result = _build_cluster_pair(
            trap={
                "type": "java.lang.Exception",
                "handler": "B3",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B3"],
            },
            trap_index=0,
            cluster_assignment={
                "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
                "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            },
            bid_to_nids={"B0": ["n0"], "B3": ["n2", "n3"]},
            block_first={"B0": "n0", "B3": "n2"},
        )
        assert result["handler_cluster"]["nodeIds"] == ["n2", "n3"]
        assert result["handler_cluster"]["role"] == ClusterRole.HANDLER

    def test_handler_entry_node_set_when_present(self):
        from ftrace_semantic import _build_cluster_pair

        result = _build_cluster_pair(
            trap={
                "type": "java.lang.Exception",
                "handler": "B3",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B3"],
            },
            trap_index=0,
            cluster_assignment={
                "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
                "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            },
            bid_to_nids={"B0": ["n0"], "B3": ["n2"]},
            block_first={"B0": "n0", "B3": "n2"},
        )
        assert result["handler_cluster"]["entryNodeId"] == "n2"
        assert result["handler_entry_nid"] == "n2"

    def test_handler_entry_node_absent_when_missing(self):
        from ftrace_semantic import _build_cluster_pair

        result = _build_cluster_pair(
            trap={
                "type": "java.lang.Exception",
                "handler": "B99",
                "coveredBlocks": ["B0"],
                "handlerBlocks": [],
            },
            trap_index=0,
            cluster_assignment={
                "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            },
            bid_to_nids={"B0": ["n0"]},
            block_first={"B0": "n0"},
        )
        assert "entryNodeId" not in result["handler_cluster"]
        assert result["handler_entry_nid"] == ""

    def test_does_not_mutate_input(self):
        import copy
        from ftrace_semantic import _build_cluster_pair

        trap = {
            "type": "java.lang.Exception",
            "handler": "B3",
            "coveredBlocks": ["B0"],
            "handlerBlocks": ["B3"],
        }
        ca = {
            "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
        }
        btn = {"B0": ["n0"], "B3": ["n2"]}
        bf = {"B0": "n0", "B3": "n2"}
        orig = (
            copy.deepcopy(trap),
            copy.deepcopy(ca),
            copy.deepcopy(btn),
            copy.deepcopy(bf),
        )
        _build_cluster_pair(trap, 0, ca, btn, bf)
        assert (trap, ca, btn, bf) == orig


class TestResolveExceptionEdgeSource:
    def test_returns_empty_when_no_handler_entry(self):
        from ftrace_semantic import _resolve_exception_edge_source

        result = _resolve_exception_edge_source(
            try_bids=["B0"],
            trap={
                "type": "X",
                "handler": "B3",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B3"],
            },
            block_first={"B0": "n0"},
            handler_entry_nid="",
        )
        assert result == ""

    def test_returns_first_try_bid_when_present(self):
        from ftrace_semantic import _resolve_exception_edge_source

        result = _resolve_exception_edge_source(
            try_bids=["B0", "B1"],
            trap={
                "type": "X",
                "handler": "B3",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B3"],
            },
            block_first={"B0": "n0", "B1": "n1", "B3": "n5"},
            handler_entry_nid="n5",
        )
        assert result == "n0"

    def test_falls_back_to_covered_blocks(self):
        from ftrace_semantic import _resolve_exception_edge_source

        result = _resolve_exception_edge_source(
            try_bids=[],
            trap={
                "type": "X",
                "handler": "B3",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B3"],
            },
            block_first={"B1": "n1", "B3": "n5"},
            handler_entry_nid="n5",
        )
        assert result == "n1"

    def test_returns_empty_when_no_covered_blocks_found(self):
        from ftrace_semantic import _resolve_exception_edge_source

        result = _resolve_exception_edge_source(
            try_bids=[],
            trap={
                "type": "X",
                "handler": "B3",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B3"],
            },
            block_first={"B3": "n5"},
            handler_entry_nid="n5",
        )
        assert result == ""


class TestBuildExceptionEdge:
    def test_builds_edge_with_correct_cluster_offsets(self):
        from ftrace_semantic import _build_exception_edge

        result = _build_exception_edge(
            src_nid="n0",
            handler_entry_nid="n5",
            etype="RuntimeException",
            cluster_offset=4,
        )
        assert len(result) == 1
        ee = result[0]
        assert ee["from"] == "n0"
        assert ee["to"] == "n5"
        assert ee["trapType"] == "RuntimeException"
        assert ee["fromCluster"] == 4
        assert ee["toCluster"] == 5

    def test_returns_empty_when_no_source(self):
        from ftrace_semantic import _build_exception_edge

        result = _build_exception_edge(
            src_nid="",
            handler_entry_nid="n5",
            etype="RuntimeException",
            cluster_offset=0,
        )
        assert result == []

    def test_does_not_mutate_input(self):
        """No mutable args to mutate — this just verifies the pure-function contract."""
        from ftrace_semantic import _build_exception_edge

        result1 = _build_exception_edge("n0", "n5", "X", 0)
        result2 = _build_exception_edge("n0", "n5", "X", 0)
        assert result1 == result2


def _collect_all_node_ids(tree: dict) -> list[str]:
    """Recursively collect all node IDs from a semantic tree."""
    ids = [n["id"] for n in tree.get("nodes", [])]
    for child in tree.get("children", []):
        ids.extend(_collect_all_node_ids(child))
    return ids


class TestNodeCounterThreading:
    def test_children_get_unique_node_ids(self):
        """Children must receive sequential non-overlapping ID ranges.

        The old `i * 100` stride causes collisions when a child has >100 nodes.
        With sequential counter threading, all IDs must be globally unique.
        """
        from ftrace_semantic import build_semantic_graph_pass
        from ftrace_types import NodeCounter

        # Build a child with 3 blocks (3 nodes) — simple enough to construct
        def _make_child(method_name: str, call_site_line: int):
            return {
                "class": "com.example.Svc",
                "method": method_name,
                "methodSignature": f"<com.example.Svc: void {method_name}()>",
                "lineStart": 1,
                "lineEnd": 10,
                "sourceLineCount": 10,
                "blocks": [
                    {
                        "id": "B0",
                        "stmts": [],
                        "mergedStmts": [
                            {"line": 1, "calls": [], "branches": [], "assigns": []},
                        ],
                    },
                    {
                        "id": "B1",
                        "stmts": [],
                        "mergedStmts": [
                            {"line": 5, "calls": [], "branches": [], "assigns": []},
                        ],
                    },
                    {
                        "id": "B2",
                        "stmts": [],
                        "mergedStmts": [
                            {"line": 10, "calls": [], "branches": [], "assigns": []},
                        ],
                    },
                ],
                "edges": [
                    {"fromBlock": "B0", "toBlock": "B1"},
                    {"fromBlock": "B1", "toBlock": "B2"},
                ],
                "traps": [],
                "metadata": {"clusterAssignment": {}},
                "children": [],
                "callSiteLine": call_site_line,
            }

        parent = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {
                            "line": 1,
                            "calls": ["Svc.child1"],
                            "branches": [],
                            "assigns": [],
                        },
                        {
                            "line": 2,
                            "calls": ["Svc.child2"],
                            "branches": [],
                            "assigns": [],
                        },
                        {
                            "line": 3,
                            "calls": ["Svc.child3"],
                            "branches": [],
                            "assigns": [],
                        },
                    ],
                },
            ],
            traps=[],
            cluster_assignment={},
            children=[
                _make_child("child1", 1),
                _make_child("child2", 2),
                _make_child("child3", 3),
            ],
        )

        result, counter = build_semantic_graph_pass(parent, NodeCounter())
        all_ids = _collect_all_node_ids(result)

        # All IDs must be unique
        assert len(all_ids) == len(set(all_ids)), (
            f"Duplicate node IDs found: "
            f"{[nid for nid in all_ids if all_ids.count(nid) > 1]}"
        )
        # Parent has 3 nodes, each child has 3 nodes = 12 total
        assert len(all_ids) == 12

    def test_build_semantic_graph_pass_returns_tuple(self):
        """build_semantic_graph_pass must return (MethodSemanticCFG, NodeCounter)."""
        from ftrace_semantic import build_semantic_graph_pass
        from ftrace_types import NodeCounter

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []},
                    ],
                },
            ],
            traps=[],
            cluster_assignment={},
        )
        result, counter = build_semantic_graph_pass(tree, NodeCounter())
        assert isinstance(counter, NodeCounter)
        assert counter.value >= 1
        assert "nodes" in result

    def test_leaf_returns_zero_advance_counter(self):
        """Leaf nodes consume no IDs — counter should pass through unchanged."""
        from ftrace_semantic import build_semantic_graph_pass
        from ftrace_types import NodeCounter

        tree = {
            "class": "Svc",
            "method": "run",
            "methodSignature": "sig",
            "ref": True,
        }
        result, counter = build_semantic_graph_pass(tree, NodeCounter(42))
        assert counter.value == 42
        assert result.get("ref") is True
