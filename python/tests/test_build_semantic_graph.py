"""Tests for pass 4: build_semantic_graph."""

from ftrace_types import (
    SemanticNode,
    SemanticEdge,
    SemanticCluster,
    ExceptionEdge,
    NodeKind,
    ClusterRole,
)


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
        result = transform(tree)

        # Should have semantic fields
        assert "nodes" in result
        assert "edges" in result
        assert "clusters" in result
        assert "exceptionEdges" in result

        # Should not have raw fields
        assert "blocks" not in result
        assert "traps" not in result

    def test_transform_leaf_node(self):
        from ftrace_semantic import transform

        tree = {"class": "Svc", "method": "run", "methodSignature": "sig", "ref": True}
        result = transform(tree)
        assert result.get("ref") is True
        assert "nodes" not in result
