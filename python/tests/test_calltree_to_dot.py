"""Tests for calltree_to_dot with flat {nodes, calls} schema."""

SIG_A = "<com.example.A: void foo()>"
SIG_B = "<com.example.B: void bar()>"
SIG_C = "<com.example.C: void baz()>"


def _node(cls: str, method: str) -> dict:
    return {
        "class": cls,
        "method": method,
        "methodSignature": f"<{cls}: void {method}()>",
    }


class TestCollectNodesFlat:
    def test_all_in_scope_nodes_included(self):
        from calltree_to_dot import collect_nodes_flat

        nodes = {
            SIG_A: _node("com.example.A", "foo"),
            SIG_B: _node("com.example.B", "bar"),
        }
        result = collect_nodes_flat(nodes)
        assert SIG_A in result
        assert SIG_B in result

    def test_returns_frozenset(self):
        from calltree_to_dot import collect_nodes_flat

        result = collect_nodes_flat({SIG_A: _node("com.example.A", "foo")})
        assert isinstance(result, frozenset)


class TestCollectEdgesFlat:
    def test_normal_calls_included(self):
        from calltree_to_dot import collect_edges_flat

        calls = [{"from": SIG_A, "to": SIG_B, "callSiteLine": 10}]
        edges, cycle_edges = collect_edges_flat(calls)
        assert (SIG_A, SIG_B) in edges

    def test_filtered_calls_excluded(self):
        from calltree_to_dot import collect_edges_flat

        calls = [{"from": SIG_A, "to": SIG_B, "filtered": True}]
        edges, cycle_edges = collect_edges_flat(calls)
        assert (SIG_A, SIG_B) not in edges

    def test_cycle_calls_in_cycle_set(self):
        from calltree_to_dot import collect_edges_flat

        calls = [{"from": SIG_A, "to": SIG_B, "cycle": True}]
        edges, cycle_edges = collect_edges_flat(calls)
        assert (SIG_A, SIG_B) not in edges
        assert (SIG_A, SIG_B) in cycle_edges


class TestRenderDotFlat:
    def test_includes_node_labels(self):
        from calltree_to_dot import render_dot

        node_sigs = frozenset({SIG_A})
        label_map = {SIG_A: "A.foo"}
        dot = render_dot(node_sigs, frozenset(), frozenset(), label_map)
        assert 'label="A.foo"' in dot

    def test_normal_edges_solid(self):
        from calltree_to_dot import render_dot

        sigs = frozenset({SIG_A, SIG_B})
        edges = frozenset({(SIG_A, SIG_B)})
        dot = render_dot(sigs, edges, frozenset(), {SIG_A: "A.foo", SIG_B: "B.bar"})
        assert "->" in dot
        assert "dashed" not in dot

    def test_cycle_edges_dashed(self):
        from calltree_to_dot import render_dot

        sigs = frozenset({SIG_A})
        cycle_edges = frozenset({(SIG_A, SIG_A)})
        dot = render_dot(sigs, frozenset(), cycle_edges, {SIG_A: "A.foo"})
        assert "dashed" in dot

    def test_roots_get_distinct_shape(self):
        from calltree_to_dot import render_dot, find_roots

        # SIG_A has no incoming edges → root
        nodes = frozenset({SIG_A, SIG_B})
        calls = [{"from": SIG_A, "to": SIG_B}]
        roots = find_roots(nodes, calls)
        assert SIG_A in roots
        assert SIG_B not in roots
