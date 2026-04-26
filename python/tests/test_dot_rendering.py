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


def _quoted_value(line: str, key: str) -> str:
    tag = f'{key}="'
    start = line.find(tag)
    if start == -1:
        return ""
    start += len(tag)
    end = line.index('"', start)
    return line[start:end]


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
