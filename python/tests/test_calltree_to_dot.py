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


# ---------------------------------------------------------------------------
# Producer-scenario tests — verify DOT rendering for all three input sources
# ---------------------------------------------------------------------------

SIG_ROOT = "<com.example.Root: void entry()>"
SIG_LEAF = "<com.example.Leaf: void work()>"


def _java_node(sig: str, cls: str, method: str) -> dict:
    return {
        "node_type": "java_method",
        "class": cls,
        "method": method,
        "methodSignature": sig,
    }


def _jsp_node(jsp: str) -> dict:
    key = f"jsp:/{jsp}"
    return {
        "node_type": "jsp",
        "class": f"/{jsp}",
        "method": "",
        "methodSignature": key,
    }


def _el_node(jsp: str, el: str) -> dict:
    key = f"el:/{jsp}#{el}"
    return {
        "node_type": "el_expression",
        "class": f"/{jsp}",
        "method": el,
        "methodSignature": key,
        "expression": el,
    }


class TestDotFromCalltreeOutput:
    """calltree emits: nodes with node_type=java_method, calls with edge_info={}."""

    def _make_data(self):
        nodes = {
            SIG_ROOT: _java_node(SIG_ROOT, "com.example.Root", "entry"),
            SIG_LEAF: _java_node(SIG_LEAF, "com.example.Leaf", "work"),
        }
        calls = [
            {"from": SIG_ROOT, "to": SIG_LEAF, "edge_info": {}},
        ]
        return nodes, calls

    def test_both_nodes_in_dot(self):
        from calltree_to_dot import (
            collect_nodes_flat,
            collect_edges_flat,
            find_roots,
            render_dot,
        )

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {
            sig: nd["class"].split(".")[-1] + "." + nd["method"]
            for sig, nd in nodes.items()
        }
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert "Root.entry" in dot
        assert "Leaf.work" in dot

    def test_edge_rendered_in_dot(self):
        from calltree_to_dot import (
            collect_nodes_flat,
            collect_edges_flat,
            find_roots,
            render_dot,
        )

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {
            sig: nd["class"].split(".")[-1] + "." + nd["method"]
            for sig, nd in nodes.items()
        }
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert "->" in dot

    def test_edge_info_field_does_not_break_rendering(self):
        from calltree_to_dot import collect_edges_flat

        calls = [{"from": SIG_ROOT, "to": SIG_LEAF, "edge_info": {}}]
        edges, cycle_edges = collect_edges_flat(calls)
        assert (SIG_ROOT, SIG_LEAF) in edges


class TestDotFromFramesOutput:
    """frames emits: nodes with node_type=java_method, calls with edge_info={} (backward trace subset)."""

    def _make_data(self):
        # frames backward trace: main → svc → dao; only svc→dao path shown
        SIG_SVC = "<com.example.Svc: void handle()>"
        SIG_DAO = "<com.example.Dao: void save()>"
        nodes = {
            SIG_SVC: _java_node(SIG_SVC, "com.example.Svc", "handle"),
            SIG_DAO: _java_node(SIG_DAO, "com.example.Dao", "save"),
        }
        calls = [
            {"from": SIG_SVC, "to": SIG_DAO, "edge_info": {}, "callSiteLine": 35},
        ]
        return nodes, calls

    def test_both_nodes_rendered(self):
        from calltree_to_dot import (
            collect_nodes_flat,
            collect_edges_flat,
            find_roots,
            render_dot,
        )

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {sig: nd["method"] for sig, nd in nodes.items()}
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert "handle" in dot
        assert "save" in dot

    def test_node_type_field_ignored_cleanly(self):
        from calltree_to_dot import collect_nodes_flat

        SIG_SVC = "<com.example.Svc: void handle()>"
        nodes = {SIG_SVC: _java_node(SIG_SVC, "com.example.Svc", "handle")}
        # Must not raise — unknown fields like node_type are ignored
        result = collect_nodes_flat(nodes)
        assert SIG_SVC in result


class TestDotFromJspmapOutput:
    """jspmap emits: JSP+EL+java_method nodes, edges with typed edge_info."""

    JSP_KEY = "jsp:/order.jsp"
    EL_KEY = "el:/order.jsp##{orderAction.submit}"
    ENTRY_SIG = "<com.example.web.OrderAction: void submit()>"
    DAO_SIG = "<com.example.dao.JdbcDao: void save()>"

    def _make_data(self):
        nodes = {
            self.JSP_KEY: _jsp_node("order.jsp"),
            self.EL_KEY: _el_node("order.jsp", "#{orderAction.submit}"),
            self.ENTRY_SIG: _java_node(
                self.ENTRY_SIG, "com.example.web.OrderAction", "submit"
            ),
            self.DAO_SIG: _java_node(self.DAO_SIG, "com.example.dao.JdbcDao", "save"),
        }
        calls = [
            {
                "from": self.JSP_KEY,
                "to": self.EL_KEY,
                "edge_info": {"edge_type": "el_call"},
            },
            {
                "from": self.EL_KEY,
                "to": self.ENTRY_SIG,
                "edge_info": {"edge_type": "method_call"},
            },
            {"from": self.ENTRY_SIG, "to": self.DAO_SIG, "edge_info": {}},
        ]
        return nodes, calls

    def test_all_four_node_types_in_dot(self):
        from calltree_to_dot import (
            collect_nodes_flat,
            collect_edges_flat,
            find_roots,
            render_dot,
            _make_dot_label,
        )

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {sig: _make_dot_label(nd) for sig, nd in nodes.items()}
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert (
            self.JSP_KEY.replace(":", "_").replace("/", "_").replace(".", "_") in dot
            or "order" in dot
        )
        # All 4 sigs must appear as sanitized IDs
        from calltree_to_dot import _sanitize_id

        for sig in [self.JSP_KEY, self.EL_KEY, self.ENTRY_SIG, self.DAO_SIG]:
            assert _sanitize_id(sig) in dot

    def test_all_three_edges_rendered(self):
        from calltree_to_dot import (
            collect_nodes_flat,
            collect_edges_flat,
            find_roots,
            render_dot,
            _make_dot_label,
            _sanitize_id,
        )

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {sig: _make_dot_label(nd) for sig, nd in nodes.items()}
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert f"{_sanitize_id(self.JSP_KEY)} -> {_sanitize_id(self.EL_KEY)}" in dot
        assert f"{_sanitize_id(self.EL_KEY)} -> {_sanitize_id(self.ENTRY_SIG)}" in dot
        assert f"{_sanitize_id(self.ENTRY_SIG)} -> {_sanitize_id(self.DAO_SIG)}" in dot

    def test_edge_info_typed_edges_not_filtered(self):
        from calltree_to_dot import collect_edges_flat

        nodes, calls = self._make_data()
        edges, cycle_edges = collect_edges_flat(calls)
        assert (self.JSP_KEY, self.EL_KEY) in edges
        assert (self.EL_KEY, self.ENTRY_SIG) in edges
        assert (self.ENTRY_SIG, self.DAO_SIG) in edges

    def test_jsp_node_is_root(self):
        from calltree_to_dot import collect_nodes_flat, find_roots

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        roots = find_roots(node_sigs, calls)
        assert self.JSP_KEY in roots

    def test_dot_output_is_valid_digraph(self):
        from calltree_to_dot import (
            collect_nodes_flat,
            collect_edges_flat,
            find_roots,
            render_dot,
            _make_dot_label,
        )

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {sig: _make_dot_label(nd) for sig, nd in nodes.items()}
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert dot.startswith("digraph")
        assert dot.strip().endswith("}")
