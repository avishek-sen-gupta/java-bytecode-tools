"""Tests for ftrace_semantic_to_dot: DOT rendering of semantic CFG trees."""

from copy import deepcopy

from ftrace_semantic_to_dot import (
    _count_tree,
    _render_edge,
    _render_exception_edge,
    _render_leaf,
    _render_node,
    _render_trap_cluster,
    build_dot,
    escape,
)
from ftrace_types import (
    ClusterRole,
    ExceptionEdge,
    MethodSemanticCFG,
    NodeKind,
    SemanticCluster,
    SemanticEdge,
    SemanticNode,
)

# --- Fixtures ---


def _semantic_node(
    nid: str = "n0",
    lines: list[int] = [],
    kind: NodeKind = NodeKind.PLAIN,
    label: list[str] = ["L10"],
) -> SemanticNode:
    return {"id": nid, "lines": list(lines), "kind": kind, "label": list(label)}


def _semantic_edge(src: str = "n0", dst: str = "n1", branch: str = "") -> SemanticEdge:
    edge: SemanticEdge = {"from": src, "to": dst}
    if branch:
        edge["branch"] = branch
    return edge


def _leaf_method(leaf_kind: str = "ref") -> MethodSemanticCFG:
    result: dict = {"class": "com.example.Foo", "method": "bar"}
    result[leaf_kind] = True
    return result


def _simple_method(
    nodes: list[SemanticNode] = [],
    edges: list[SemanticEdge] = [],
    children: list[MethodSemanticCFG] = [],
) -> MethodSemanticCFG:
    result: dict = {
        "class": "com.example.Svc",
        "method": "handle",
        "nodes": list(nodes),
        "edges": list(edges),
        "clusters": [],
        "exceptionEdges": [],
        "lineStart": 10,
        "lineEnd": 20,
    }
    if children:
        result["children"] = list(children)
    if nodes:
        result["entryNodeId"] = nodes[0]["id"]
    return result


# --- escape ---


class TestEscape:
    def test_quotes_escaped(self):
        assert escape('"hello"') == '\\"hello\\"'

    def test_backslash_escaped(self):
        assert escape("a\\b") == "a\\\\b"

    def test_newline_escaped(self):
        assert escape("line1\nline2") == "line1\\nline2"

    def test_plain_string_unchanged(self):
        assert escape("hello world") == "hello world"


# --- _render_node ---


class TestRenderNode:
    def test_plain_node(self):
        node = _semantic_node(nid="n0", label=["L10", "x = 42"])
        result = _render_node("n0", node)
        assert "n0 [" in result
        assert 'label="L10\\nx = 42"' in result
        assert 'shape="box"' in result

    def test_call_node_has_green_fill(self):
        node = _semantic_node(kind=NodeKind.CALL, label=["L15", "Dao.query"])
        result = _render_node("n0", node)
        assert "#d4edda" in result

    def test_branch_node_has_diamond_shape(self):
        node = _semantic_node(kind=NodeKind.BRANCH, label=["L20", "x > 0"])
        result = _render_node("n0", node)
        assert "diamond" in result

    def test_cycle_node_has_red_fill(self):
        node = _semantic_node(kind=NodeKind.CYCLE, label=["cycle"])
        result = _render_node("n0", node)
        assert "#ffcccc" in result
        assert "dashed" in result

    def test_ref_node_has_gray_fill(self):
        node = _semantic_node(kind=NodeKind.REF, label=["ref"])
        result = _render_node("n0", node)
        assert "#e8e8e8" in result


# --- _render_edge ---


class TestRenderEdge:
    def test_plain_edge(self):
        edge = _semantic_edge("n0", "n1")
        result = _render_edge(edge)
        assert result == "    n0 -> n1;"

    def test_true_branch_edge(self):
        edge = _semantic_edge("n0", "n1", branch="T")
        result = _render_edge(edge)
        assert 'label="T"' in result
        assert "#28a745" in result  # green

    def test_false_branch_edge(self):
        edge = _semantic_edge("n0", "n1", branch="F")
        result = _render_edge(edge)
        assert 'label="F"' in result
        assert "#dc3545" in result  # red


# --- _render_exception_edge ---


class TestRenderExceptionEdge:
    def test_basic_exception_edge(self):
        ee: ExceptionEdge = {
            "from": "n0",
            "to": "n5",
            "trapType": "IOException",
            "fromCluster": 0,
            "toCluster": 1,
        }
        clusters: list[SemanticCluster] = [
            {"trapType": "IOException", "role": ClusterRole.TRY, "nodeIds": ["n0"]},
            {
                "trapType": "IOException",
                "role": ClusterRole.HANDLER,
                "nodeIds": ["n5"],
            },
        ]
        result = _render_exception_edge(ee, clusters, 0)
        assert "n0 -> n5" in result
        assert "IOException" in result
        assert "#ffa500" in result  # orange
        assert "dashed" in result

    def test_cluster_references(self):
        ee: ExceptionEdge = {
            "from": "n0",
            "to": "n5",
            "trapType": "Exception",
            "fromCluster": 0,
            "toCluster": 1,
        }
        clusters: list[SemanticCluster] = [
            {"trapType": "Exception", "role": ClusterRole.TRY, "nodeIds": ["n0"]},
            {"trapType": "Exception", "role": ClusterRole.HANDLER, "nodeIds": ["n5"]},
        ]
        result = _render_exception_edge(ee, clusters, 3)
        assert "cluster_trap_3_0" in result
        assert "cluster_trap_3_1" in result


# --- _render_leaf ---


class TestRenderLeaf:
    def test_ref_leaf(self):
        node = _leaf_method("ref")
        lines, nid, next_counter = _render_leaf(node, 0)
        assert len(lines) == 1
        assert "Foo.bar" in lines[0]
        assert "(ref)" in lines[0]
        assert nid == "n_leaf_0"
        assert next_counter == 1

    def test_cycle_leaf(self):
        node = _leaf_method("cycle")
        lines, nid, _ = _render_leaf(node, 5)
        assert "(cycle)" in lines[0]
        assert nid == "n_leaf_5"

    def test_filtered_leaf(self):
        node = _leaf_method("filtered")
        lines, nid, _ = _render_leaf(node, 0)
        assert "(filtered)" in lines[0]

    def test_non_leaf_returns_empty(self):
        node: MethodSemanticCFG = {"class": "com.Foo", "method": "bar"}
        lines, nid, counter = _render_leaf(node, 0)
        assert lines == []
        assert nid == ""
        assert counter == 0


# --- _render_trap_cluster ---


class TestRenderTrapCluster:
    def test_try_cluster(self):
        cluster: SemanticCluster = {
            "trapType": "IOException",
            "role": ClusterRole.TRY,
            "nodeIds": ["n0", "n1"],
        }
        lines = _render_trap_cluster(0, cluster, 0)
        joined = "\n".join(lines)
        assert "cluster_trap_0_0" in joined
        assert "try (IOException)" in joined
        assert "n0;" in joined
        assert "n1;" in joined

    def test_handler_cluster_catch(self):
        cluster: SemanticCluster = {
            "trapType": "IOException",
            "role": ClusterRole.HANDLER,
            "nodeIds": ["n5"],
        }
        lines = _render_trap_cluster(1, cluster, 0)
        joined = "\n".join(lines)
        assert "catch (IOException)" in joined

    def test_handler_cluster_finally(self):
        cluster: SemanticCluster = {
            "trapType": "Throwable",
            "role": ClusterRole.HANDLER,
            "nodeIds": ["n5"],
        }
        lines = _render_trap_cluster(1, cluster, 0)
        joined = "\n".join(lines)
        assert "finally" in joined


# --- _count_tree ---


class TestCountTree:
    def test_single_method(self):
        method = _simple_method(nodes=[_semantic_node("n0"), _semantic_node("n1")])
        methods, nodes = _count_tree(method)
        assert methods == 1
        assert nodes == 2

    def test_with_children(self):
        child = _simple_method(nodes=[_semantic_node("n2")])
        parent = _simple_method(
            nodes=[_semantic_node("n0"), _semantic_node("n1")],
            children=[child],
        )
        methods, nodes = _count_tree(parent)
        assert methods == 2
        assert nodes == 3

    def test_empty_method(self):
        method = _simple_method()
        methods, nodes = _count_tree(method)
        assert methods == 1
        assert nodes == 0


# --- build_dot ---


class TestBuildDot:
    def test_digraph_structure(self):
        method = _simple_method(nodes=[_semantic_node("n0", label=["L10", "x = 42"])])
        dot = build_dot(method)
        assert dot.startswith("digraph ftrace {")
        assert dot.strip().endswith("}")

    def test_contains_rankdir(self):
        method = _simple_method()
        dot = build_dot(method)
        assert "rankdir=TB" in dot

    def test_contains_subgraph_cluster(self):
        method = _simple_method(nodes=[_semantic_node("n0")])
        dot = build_dot(method)
        assert "subgraph cluster_0" in dot

    def test_method_label_in_subgraph(self):
        method = _simple_method(nodes=[_semantic_node("n0")])
        dot = build_dot(method)
        assert "Svc.handle" in dot

    def test_splines_option(self):
        method = _simple_method()
        dot = build_dot(method, splines="ortho")
        assert 'splines="ortho"' in dot

    def test_no_splines_by_default(self):
        method = _simple_method()
        dot = build_dot(method)
        assert "splines" not in dot

    def test_edges_rendered(self):
        nodes = [_semantic_node("n0"), _semantic_node("n1")]
        edges = [_semantic_edge("n0", "n1")]
        method = _simple_method(nodes=nodes, edges=edges)
        dot = build_dot(method)
        assert "n0 -> n1" in dot

    def test_leaf_child_rendered(self):
        child = _leaf_method("ref")
        child["callSiteLine"] = 15
        parent = _simple_method(
            nodes=[_semantic_node("n0", lines=[15])],
            children=[child],
        )
        dot = build_dot(parent)
        assert "n_leaf_" in dot
        assert "(ref)" in dot

    def test_does_not_mutate_inputs(self):
        nodes = [_semantic_node("n0"), _semantic_node("n1")]
        edges = [_semantic_edge("n0", "n1")]
        method = _simple_method(nodes=nodes, edges=edges)
        method_copy = deepcopy(method)
        build_dot(method)
        assert method == method_copy
