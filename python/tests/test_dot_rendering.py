"""Tests for the rewritten ftrace_to_dot — dumb semantic JSON → DOT renderer."""


def _make_semantic_method(nodes, edges, clusters=(), exception_edges=(), children=()):
    return {
        "class": "com.example.Svc",
        "method": "handle",
        "lineStart": 1,
        "lineEnd": 20,
        "nodes": nodes,
        "edges": edges,
        "clusters": list(clusters),
        "exceptionEdges": list(exception_edges),
        "children": list(children),
    }


class TestNodeRendering:
    def test_plain_node(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}],
            edges=[],
        )
        dot = build_dot(method)
        assert 'label="L5"' in dot
        assert 'fillcolor="white"' in dot

    def test_call_node_green(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [9], "kind": "call", "label": ["L9", "Foo.bar"]}
            ],
            edges=[],
        )
        dot = build_dot(method)
        assert "#d4edda" in dot

    def test_branch_node_diamond(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [6], "kind": "branch", "label": ["L6", "i <= 0"]}
            ],
            edges=[],
        )
        dot = build_dot(method)
        assert "diamond" in dot
        assert "#cce5ff" in dot

    def test_assign_node_beige(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [7], "kind": "assign", "label": ["L7", "x = 5"]}
            ],
            edges=[],
        )
        dot = build_dot(method)
        assert "#f5f5dc" in dot

    def test_ref_node(self):
        from ftrace_to_dot import build_dot

        method = {
            "class": "com.example.Svc",
            "method": "run",
            "ref": True,
            "methodSignature": "sig",
        }
        dot = build_dot(method)
        assert "(ref)" in dot
        assert "#e8e8e8" in dot

    def test_cycle_node(self):
        from ftrace_to_dot import build_dot

        method = {
            "class": "com.example.Svc",
            "method": "run",
            "cycle": True,
            "methodSignature": "sig",
        }
        dot = build_dot(method)
        assert "(cycle)" in dot
        assert "#ffcccc" in dot

    def test_filtered_node(self):
        from ftrace_to_dot import build_dot

        method = {
            "class": "com.example.Svc",
            "method": "run",
            "filtered": True,
            "methodSignature": "sig",
        }
        dot = build_dot(method)
        assert "(filtered)" in dot
        assert "#fff3cd" in dot

    def test_multiline_label(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {
                    "id": "n0",
                    "lines": [9],
                    "kind": "call",
                    "label": ["L9", "RuntimeException.<init>"],
                }
            ],
            edges=[],
        )
        dot = build_dot(method)
        assert r"L9\nRuntimeException.<init>" in dot


class TestEdgeRendering:
    def test_normal_edge(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]},
                {"id": "n1", "lines": [6], "kind": "plain", "label": ["L6"]},
            ],
            edges=[{"from": "n0", "to": "n1"}],
        )
        dot = build_dot(method)
        assert "n0 -> n1;" in dot

    def test_branch_true_edge(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [6], "kind": "branch", "label": ["L6"]},
                {"id": "n1", "lines": [7], "kind": "plain", "label": ["L7"]},
            ],
            edges=[{"from": "n0", "to": "n1", "branch": "T"}],
        )
        dot = build_dot(method)
        assert "#28a745" in dot
        assert 'label="T"' in dot

    def test_branch_false_edge(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [6], "kind": "branch", "label": ["L6"]},
                {"id": "n1", "lines": [9], "kind": "plain", "label": ["L9"]},
            ],
            edges=[{"from": "n0", "to": "n1", "branch": "F"}],
        )
        dot = build_dot(method)
        assert "#dc3545" in dot
        assert 'label="F"' in dot


class TestClusterRendering:
    def test_try_cluster_orange(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}],
            edges=[],
            clusters=[
                {"trapType": "RuntimeException", "role": "try", "nodeIds": ["n0"]},
            ],
        )
        dot = build_dot(method)
        assert "#ffa500" in dot
        assert "try (RuntimeException)" in dot

    def test_handler_cluster_catch(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [11], "kind": "plain", "label": ["L11"]}],
            edges=[],
            clusters=[
                {
                    "trapType": "RuntimeException",
                    "role": "handler",
                    "nodeIds": ["n0"],
                    "entryNodeId": "n0",
                },
            ],
        )
        dot = build_dot(method)
        assert "#007bff" in dot
        assert "catch (RuntimeException)" in dot

    def test_handler_cluster_finally(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [14], "kind": "plain", "label": ["L14"]}],
            edges=[],
            clusters=[
                {
                    "trapType": "Throwable",
                    "role": "handler",
                    "nodeIds": ["n0"],
                    "entryNodeId": "n0",
                },
            ],
        )
        dot = build_dot(method)
        assert "finally" in dot


class TestExceptionEdgeRendering:
    def test_exception_edge_dashed_orange(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]},
                {"id": "n1", "lines": [11], "kind": "plain", "label": ["L11"]},
            ],
            edges=[],
            clusters=[
                {"trapType": "RuntimeException", "role": "try", "nodeIds": ["n0"]},
                {
                    "trapType": "RuntimeException",
                    "role": "handler",
                    "nodeIds": ["n1"],
                    "entryNodeId": "n1",
                },
            ],
            exception_edges=[
                {
                    "from": "n0",
                    "to": "n1",
                    "trapType": "RuntimeException",
                    "fromCluster": 0,
                    "toCluster": 1,
                },
            ],
        )
        dot = build_dot(method)
        assert "n0 -> n1" in dot
        assert "dashed" in dot
        assert "#ffa500" in dot
        assert "RuntimeException" in dot


class TestMethodCluster:
    def test_method_label(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}],
            edges=[],
        )
        dot = build_dot(method)
        assert "Svc.handle [1-20]" in dot
        assert "#f0f0f0" in dot


class TestCrossClusterEdges:
    def test_child_call_edge(self):
        from ftrace_to_dot import build_dot

        child = {
            "class": "com.example.Other",
            "method": "run",
            "lineStart": 30,
            "lineEnd": 40,
            "entryNodeId": "n5",
            "nodes": [{"id": "n5", "lines": [30], "kind": "plain", "label": ["L30"]}],
            "edges": [],
            "clusters": [],
            "exceptionEdges": [],
            "children": [],
            "callSiteLine": 9,
        }
        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]},
                {
                    "id": "n1",
                    "lines": [9],
                    "kind": "call",
                    "label": ["L9", "Other.run"],
                },
            ],
            edges=[{"from": "n0", "to": "n1"}],
            children=[child],
        )
        dot = build_dot(method)
        assert "n1 -> n5" in dot
        assert "#e05050" in dot


class TestRenderLeaf:
    def test_ref_leaf(self):
        from ftrace_to_dot import _render_leaf

        node = {"class": "com.example.Svc", "method": "run", "ref": True}
        lines, nid, next_counter = _render_leaf(node, 5)
        assert len(lines) == 1
        assert "n_leaf_5" in lines[0]
        assert "(ref)" in lines[0]
        assert "#e8e8e8" in lines[0]
        assert nid == "n_leaf_5"
        assert next_counter == 6

    def test_cycle_leaf(self):
        from ftrace_to_dot import _render_leaf

        node = {"class": "com.example.Svc", "method": "run", "cycle": True}
        lines, nid, next_counter = _render_leaf(node, 0)
        assert len(lines) == 1
        assert "n_leaf_0" in lines[0]
        assert "(cycle)" in lines[0]
        assert "#ffcccc" in lines[0]
        assert nid == "n_leaf_0"
        assert next_counter == 1

    def test_filtered_leaf(self):
        from ftrace_to_dot import _render_leaf

        node = {"class": "com.example.Svc", "method": "run", "filtered": True}
        lines, nid, next_counter = _render_leaf(node, 3)
        assert len(lines) == 1
        assert "(filtered)" in lines[0]
        assert "#fff3cd" in lines[0]
        assert nid == "n_leaf_3"
        assert next_counter == 4

    def test_non_leaf_returns_empty(self):
        from ftrace_to_dot import _render_leaf

        node = {"class": "com.example.Svc", "method": "run"}
        lines, nid, next_counter = _render_leaf(node, 7)
        assert lines == []
        assert nid == ""
        assert next_counter == 7


class TestRenderTrapCluster:
    def test_try_cluster(self):
        from ftrace_to_dot import _render_trap_cluster

        cluster = {
            "trapType": "RuntimeException",
            "role": "try",
            "nodeIds": ["n0", "n1"],
        }
        lines = _render_trap_cluster(0, cluster)
        assert "subgraph cluster_trap_0 {" in lines[0]
        assert "try (RuntimeException)" in lines[1]
        assert "#ffa500" in lines[2]
        assert "n0;" in lines[3]
        assert "n1;" in lines[4]
        assert lines[-1] == "    }"

    def test_handler_catch(self):
        from ftrace_to_dot import _render_trap_cluster

        cluster = {
            "trapType": "RuntimeException",
            "role": "handler",
            "nodeIds": ["n2"],
            "entryNodeId": "n2",
        }
        lines = _render_trap_cluster(1, cluster)
        assert "subgraph cluster_trap_1 {" in lines[0]
        assert "catch (RuntimeException)" in lines[1]
        assert "#007bff" in lines[2]
        assert "n2;" in lines[3]
        assert lines[-1] == "    }"

    def test_handler_finally_throwable(self):
        from ftrace_to_dot import _render_trap_cluster

        cluster = {
            "trapType": "Throwable",
            "role": "handler",
            "nodeIds": ["n3"],
            "entryNodeId": "n3",
        }
        lines = _render_trap_cluster(2, cluster)
        assert "finally" in lines[1]
        assert "#007bff" in lines[2]

    def test_handler_finally_any(self):
        from ftrace_to_dot import _render_trap_cluster

        cluster = {
            "trapType": "any",
            "role": "handler",
            "nodeIds": ["n4"],
            "entryNodeId": "n4",
        }
        lines = _render_trap_cluster(3, cluster)
        assert "finally" in lines[1]

    def test_empty_node_ids(self):
        from ftrace_to_dot import _render_trap_cluster

        cluster = {"trapType": "IOException", "role": "try", "nodeIds": []}
        lines = _render_trap_cluster(0, cluster)
        assert lines[0] == "    subgraph cluster_trap_0 {"
        assert lines[-1] == "    }"
        # Only header (1) + label (1) + style (1) + footer (1) = 4 lines
        assert len(lines) == 4


class TestRenderCrossEdges:
    def test_matching_call_site_line(self):
        from ftrace_to_dot import _render_cross_edges

        nodes = [
            {"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]},
            {"id": "n1", "lines": [9], "kind": "call", "label": ["L9", "Other.run"]},
        ]
        children = [{"callSiteLine": 9, "method": "run"}]
        child_entries = ["n5"]
        result = _render_cross_edges(nodes, children, child_entries, "n0")
        assert len(result) == 1
        assert "n1 -> n5" in result[0]
        assert "#e05050" in result[0]
        assert "bold" in result[0]

    def test_fallback_to_entry_nid(self):
        from ftrace_to_dot import _render_cross_edges

        nodes = [
            {"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]},
        ]
        children = [{"callSiteLine": 99, "method": "run"}]
        child_entries = ["n5"]
        result = _render_cross_edges(nodes, children, child_entries, "n0")
        assert len(result) == 1
        assert "n0 -> n5" in result[0]

    def test_empty_child_entry_skipped(self):
        from ftrace_to_dot import _render_cross_edges

        nodes = [{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}]
        children = [{"callSiteLine": 5, "method": "run"}]
        child_entries = [""]
        result = _render_cross_edges(nodes, children, child_entries, "n0")
        assert result == []

    def test_no_children(self):
        from ftrace_to_dot import _render_cross_edges

        nodes = [{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}]
        result = _render_cross_edges(nodes, [], [], "n0")
        assert result == []

    def test_no_entry_nid_no_match(self):
        from ftrace_to_dot import _render_cross_edges

        nodes = [{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}]
        children = [{"callSiteLine": 99, "method": "run"}]
        child_entries = ["n5"]
        result = _render_cross_edges(nodes, children, child_entries, "")
        assert result == []


class TestEscape:
    def test_plain_string(self):
        from ftrace_to_dot import escape

        assert escape("hello") == "hello"

    def test_backslash(self):
        from ftrace_to_dot import escape

        assert escape("a\\b") == "a\\\\b"

    def test_double_quote(self):
        from ftrace_to_dot import escape

        assert escape('say "hi"') == 'say \\"hi\\"'

    def test_newline(self):
        from ftrace_to_dot import escape

        assert escape("line1\nline2") == "line1\\nline2"

    def test_combined(self):
        from ftrace_to_dot import escape

        assert escape('"a\\b\n"') == '\\"a\\\\b\\n\\"'

    def test_empty_string(self):
        from ftrace_to_dot import escape

        assert escape("") == ""
