"""Tests for ddg_format: parse_slice, render_ascii, render_dot."""

from copy import deepcopy

from ddg_format import (
    _build_children,
    _node_label,
    _short_method,
    parse_slice,
    render_ascii,
    render_dot,
)

# --- Fixtures ---

SIG_A = "<com.example.Svc: void handle(java.lang.String)>"
SIG_B = "<com.example.Dao: java.util.List query(int)>"


def _node(
    method: str, stmt_id: str, stmt: str, line: int = 0, kind: str = "ASSIGN"
) -> dict:
    return {
        "method": method,
        "stmtId": stmt_id,
        "stmt": stmt,
        "line": line,
        "kind": kind,
    }


def _edge(
    from_method: str,
    from_stmt: str,
    to_method: str,
    to_stmt: str,
    kind: str = "LOCAL",
) -> dict:
    return {
        "from": {"method": from_method, "stmtId": from_stmt},
        "to": {"method": to_method, "stmtId": to_stmt},
        "edge_info": {"kind": kind},
    }


SINGLE_NODE_SLICE = {
    "seed": {"method": SIG_A, "local_var": "x"},
    "nodes": [_node(SIG_A, "s1", "x = 42", 10)],
    "edges": [],
}

TWO_NODE_LOCAL_SLICE = {
    "seed": {"method": SIG_A, "local_var": "y"},
    "nodes": [
        _node(SIG_A, "s1", "x = 42", 10),
        _node(SIG_A, "s2", "y = x + 1", 11),
    ],
    "edges": [_edge(SIG_A, "s1", SIG_A, "s2", "LOCAL")],
}

INTER_PROC_SLICE = {
    "seed": {"method": SIG_B, "local_var": "q"},
    "nodes": [
        _node(SIG_A, "s1", "dao.query(val)", 20, "INVOKE"),
        _node(SIG_B, "s2", "q = param0", 5, "IDENTITY"),
        _node(SIG_B, "s3", "return results", 15, "RETURN"),
    ],
    "edges": [
        _edge(SIG_A, "s1", SIG_B, "s2", "PARAM"),
        _edge(SIG_B, "s2", SIG_B, "s3", "LOCAL"),
    ],
}


# --- _short_method ---


class TestShortMethod:
    def test_extracts_class_and_method(self):
        assert _short_method(SIG_A) == "Svc.handle"

    def test_extracts_from_return_type_sig(self):
        assert _short_method(SIG_B) == "Dao.query"

    def test_fqcn_shortened(self):
        sig = "<org.example.deep.pkg.MyClass: void run()>"
        assert _short_method(sig) == "MyClass.run"

    def test_unparseable_returns_as_is(self):
        raw = "not a soot signature"
        assert _short_method(raw) == raw


# --- _node_label ---


class TestNodeLabel:
    def test_formats_method_line_stmt(self):
        node = _node(SIG_A, "s1", "x = 42", 10)
        label = _node_label(node)
        assert label == "[Svc.handle L10] x = 42"

    def test_missing_line_defaults_zero(self):
        node = {"method": SIG_A, "stmtId": "s1", "stmt": "nop"}
        label = _node_label(node)
        assert "L0" in label


# --- parse_slice ---


class TestParseSlice:
    def test_single_node_no_edges(self):
        nodes, edges, roots = parse_slice(SINGLE_NODE_SLICE)
        assert len(nodes) == 1
        assert edges == []
        assert roots == [(SIG_A, "s1")]

    def test_two_nodes_one_edge(self):
        nodes, edges, roots = parse_slice(TWO_NODE_LOCAL_SLICE)
        assert len(nodes) == 2
        assert len(edges) == 1
        src, dst, kind = edges[0]
        assert src == (SIG_A, "s1")
        assert dst == (SIG_A, "s2")
        assert kind == "LOCAL"

    def test_roots_are_nodes_without_incoming(self):
        nodes, edges, roots = parse_slice(TWO_NODE_LOCAL_SLICE)
        assert roots == [(SIG_A, "s1")]

    def test_inter_proc_roots(self):
        nodes, edges, roots = parse_slice(INTER_PROC_SLICE)
        assert roots == [(SIG_A, "s1")]

    def test_empty_input(self):
        nodes, edges, roots = parse_slice({"nodes": [], "edges": []})
        assert nodes == {}
        assert edges == []
        assert roots == []


# --- _build_children ---


class TestBuildChildren:
    def test_builds_adjacency(self):
        _, edges, _ = parse_slice(TWO_NODE_LOCAL_SLICE)
        children = _build_children(edges)
        assert (SIG_A, "s1") in children
        assert children[(SIG_A, "s1")] == [((SIG_A, "s2"), "LOCAL")]

    def test_leaf_node_absent_from_children(self):
        _, edges, _ = parse_slice(TWO_NODE_LOCAL_SLICE)
        children = _build_children(edges)
        assert (SIG_A, "s2") not in children


# --- render_ascii ---


class TestRenderAscii:
    def test_single_root(self):
        nodes, edges, roots = parse_slice(SINGLE_NODE_SLICE)
        lines = render_ascii(nodes, edges, roots)
        assert len(lines) == 1
        assert "[Svc.handle L10] x = 42" in lines[0]

    def test_two_nodes_shows_edge_kind(self):
        nodes, edges, roots = parse_slice(TWO_NODE_LOCAL_SLICE)
        lines = render_ascii(nodes, edges, roots)
        assert any("--LOCAL-->" in line for line in lines)

    def test_inter_proc_shows_param_edge(self):
        nodes, edges, roots = parse_slice(INTER_PROC_SLICE)
        lines = render_ascii(nodes, edges, roots)
        assert any("--PARAM-->" in line for line in lines)

    def test_cycle_detection(self):
        cycle_slice = {
            "seed": {"method": SIG_A, "local_var": "x"},
            "nodes": [
                _node(SIG_A, "s0", "init = 0", 9),
                _node(SIG_A, "s1", "x = f()", 10),
                _node(SIG_A, "s2", "f = x", 11),
            ],
            "edges": [
                _edge(SIG_A, "s0", SIG_A, "s1", "LOCAL"),
                _edge(SIG_A, "s1", SIG_A, "s2", "LOCAL"),
                _edge(SIG_A, "s2", SIG_A, "s1", "LOCAL"),
            ],
        }
        nodes, edges, roots = parse_slice(cycle_slice)
        lines = render_ascii(nodes, edges, roots)
        assert any("\u21bb" in line for line in lines)

    def test_empty_slice(self):
        lines = render_ascii({}, [], [])
        assert lines == []

    def test_does_not_mutate_inputs(self):
        data = deepcopy(INTER_PROC_SLICE)
        nodes, edges, roots = parse_slice(data)
        nodes_copy = deepcopy(nodes)
        edges_copy = deepcopy(edges)
        roots_copy = deepcopy(roots)
        render_ascii(nodes, edges, roots)
        assert nodes == nodes_copy
        assert edges == edges_copy
        assert roots == roots_copy


# --- render_dot ---


class TestRenderDot:
    def test_contains_digraph(self):
        nodes, edges, _ = parse_slice(TWO_NODE_LOCAL_SLICE)
        dot = render_dot(nodes, edges)
        assert dot.startswith("digraph bwd_slice {")
        assert dot.strip().endswith("}")

    def test_contains_subgraph_cluster(self):
        nodes, edges, _ = parse_slice(TWO_NODE_LOCAL_SLICE)
        dot = render_dot(nodes, edges)
        assert "subgraph cluster_" in dot

    def test_edge_colors(self):
        nodes, edges, _ = parse_slice(INTER_PROC_SLICE)
        dot = render_dot(nodes, edges)
        assert "color=blue" in dot  # PARAM edge
        assert "color=black" in dot  # LOCAL edge

    def test_node_shapes(self):
        nodes, edges, _ = parse_slice(INTER_PROC_SLICE)
        dot = render_dot(nodes, edges)
        assert "shape=box3d" in dot  # INVOKE
        assert "shape=invhouse" in dot  # IDENTITY

    def test_inter_proc_clusters_separate(self):
        nodes, edges, _ = parse_slice(INTER_PROC_SLICE)
        dot = render_dot(nodes, edges)
        assert "cluster_0" in dot
        assert "cluster_1" in dot

    def test_empty_graph(self):
        dot = render_dot({}, [])
        assert "digraph bwd_slice {" in dot

    def test_does_not_mutate_inputs(self):
        data = deepcopy(INTER_PROC_SLICE)
        nodes, edges, _ = parse_slice(data)
        nodes_copy = deepcopy(nodes)
        edges_copy = deepcopy(edges)
        render_dot(nodes, edges)
        assert nodes == nodes_copy
        assert edges == edges_copy
