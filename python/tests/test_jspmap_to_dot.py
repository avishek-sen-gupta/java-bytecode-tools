"""Tests for jspmap_to_dot — graph building and DOT rendering."""

from jspmap_to_dot import Node, Edge, build_graph, build_dot, _stable_id

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HOP_DAO = {
    "layer": "dao",
    "class": "com.example.HibernateOrderDao",
    "method": "save",
    "signature": "<com.example.HibernateOrderDao: void save()>",
}
HOP_SERVICE = {
    "layer": "service",
    "class": "com.example.OrderServiceImpl",
    "method": "placeOrder",
    "signature": "<com.example.OrderServiceImpl: void placeOrder()>",
}
HOP_ACTION = {
    "layer": "action",
    "class": "com.example.OrderBean",
    "method": "submit",
    "signature": "<com.example.OrderBean: void submit()>",
}

ACTION_WITH_CHAIN = {
    "jsp": "pages/order.jsp",
    "el": "#{orderBean.submit}",
    "el_context": {"tag": "h:commandButton", "attribute": "action"},
    "bean": {"name": "orderBean", "class": "com.example.OrderBean", "scope": "session"},
    "entry_signature": "<com.example.OrderBean: void submit()>",
    "chains": [[HOP_ACTION, HOP_SERVICE, HOP_DAO]],
}

ACTION_NO_CHAINS = {
    "jsp": "pages/order.jsp",
    "el": "#{orderBean.name}",
    "el_context": {"tag": "_text", "attribute": "_text"},
    "bean": {"name": "orderBean", "class": "com.example.OrderBean", "scope": "session"},
    "entry_signature": None,
    "chains": [],
}

ACTION_SECOND_JSP = {
    "jsp": "pages/other.jsp",
    "el": "#{orderBean.submit}",
    "el_context": {"tag": "h:commandButton", "attribute": "action"},
    "bean": {"name": "orderBean", "class": "com.example.OrderBean", "scope": "session"},
    "entry_signature": "<com.example.OrderBean: void submit()>",
    "chains": [[HOP_ACTION, HOP_DAO]],
}


# ---------------------------------------------------------------------------
# _stable_id
# ---------------------------------------------------------------------------


class TestStableId:
    def test_same_key_gives_same_id(self):
        assert _stable_id("hop", "foo") == _stable_id("hop", "foo")

    def test_different_keys_give_different_ids(self):
        assert _stable_id("hop", "foo") != _stable_id("hop", "bar")

    def test_different_prefixes_give_different_ids(self):
        assert _stable_id("hop", "foo") != _stable_id("el", "foo")

    def test_id_is_valid_dot_identifier(self):
        nid = _stable_id("hop", "<com.example.Foo: void bar()>")
        assert all(c.isalnum() or c == "_" for c in nid)


# ---------------------------------------------------------------------------
# build_graph
# ---------------------------------------------------------------------------


class TestBuildGraphEmpty:
    def test_no_actions_gives_empty_graph(self):
        nodes, edges = build_graph({"actions": []})
        assert nodes == frozenset()
        assert edges == frozenset()

    def test_missing_actions_key_gives_empty_graph(self):
        nodes, edges = build_graph({})
        assert nodes == frozenset()
        assert edges == frozenset()


class TestBuildGraphSingleChain:
    def setup_method(self):
        self.nodes, self.edges = build_graph({"actions": [ACTION_WITH_CHAIN]})

    def test_has_jsp_node(self):
        labels = {n.label for n in self.nodes}
        assert "pages/order.jsp" in labels

    def test_has_el_node(self):
        labels = {n.label for n in self.nodes}
        assert any("orderBean.submit" in lbl for lbl in labels)

    def test_has_hop_nodes(self):
        labels = {n.label for n in self.nodes}
        assert any("HibernateOrderDao" in lbl for lbl in labels)
        assert any("OrderServiceImpl" in lbl for lbl in labels)
        assert any("OrderBean" in lbl for lbl in labels)

    def test_edge_from_jsp_to_el(self):
        jsp_id = next(n.node_id for n in self.nodes if n.label == "pages/order.jsp")
        el_id = next(n.node_id for n in self.nodes if "orderBean.submit" in n.label)
        assert Edge(jsp_id, el_id) in self.edges

    def test_edge_chain_connected(self):
        action_id = next(n.node_id for n in self.nodes if "OrderBean.submit" in n.label)
        service_id = next(
            n.node_id for n in self.nodes if "OrderServiceImpl" in n.label
        )
        dao_id = next(n.node_id for n in self.nodes if "HibernateOrderDao" in n.label)
        assert Edge(action_id, service_id) in self.edges
        assert Edge(service_id, dao_id) in self.edges


class TestBuildGraphNoChains:
    def test_el_node_present_even_with_no_chains(self):
        nodes, edges = build_graph({"actions": [ACTION_NO_CHAINS]})
        labels = {n.label for n in nodes}
        assert any("orderBean.name" in lbl for lbl in labels)

    def test_no_hop_edges_when_no_chains(self):
        nodes, _ = build_graph({"actions": [ACTION_NO_CHAINS]})
        # Only JSP and EL nodes — no hop nodes
        assert len(nodes) == 2


class TestBuildGraphDedup:
    def test_shared_hop_produces_one_node(self):
        # Both actions share HOP_ACTION (same signature)
        action2 = {**ACTION_WITH_CHAIN, "el": "#{orderBean.other}"}
        nodes, _ = build_graph({"actions": [ACTION_WITH_CHAIN, action2]})
        action_nodes = [n for n in nodes if "OrderBean.submit" in n.label]
        assert len(action_nodes) == 1

    def test_duplicate_chains_not_duplicated(self):
        # Same chain repeated twice in one action
        action = {**ACTION_WITH_CHAIN, "chains": [ACTION_WITH_CHAIN["chains"][0]] * 3}
        nodes1, edges1 = build_graph({"actions": [ACTION_WITH_CHAIN]})
        nodes2, edges2 = build_graph({"actions": [action]})
        assert nodes1 == nodes2
        assert edges1 == edges2

    def test_two_jsps_two_jsp_nodes(self):
        nodes, _ = build_graph({"actions": [ACTION_WITH_CHAIN, ACTION_SECOND_JSP]})
        jsp_nodes = [n for n in nodes if ".jsp" in n.label]
        assert len(jsp_nodes) == 2


class TestBuildGraphDoesNotMutateInput:
    def test_does_not_mutate_input(self):
        data = {
            "actions": [
                {**ACTION_WITH_CHAIN, "chains": [list(ACTION_WITH_CHAIN["chains"][0])]}
            ]
        }
        import copy

        original = copy.deepcopy(data)
        build_graph(data)
        assert data == original


# ---------------------------------------------------------------------------
# Node layer colours
# ---------------------------------------------------------------------------


class TestNodeLayerColors:
    def setup_method(self):
        self.nodes, _ = build_graph({"actions": [ACTION_WITH_CHAIN]})

    def _node_by_label_fragment(self, fragment: str) -> Node:
        return next(n for n in self.nodes if fragment in n.label)

    def test_dao_node_has_distinct_color(self):
        dao = self._node_by_label_fragment("HibernateOrderDao")
        action = self._node_by_label_fragment("OrderBean.submit")
        assert dao.color != action.color

    def test_jsp_node_has_distinct_color(self):
        jsp = self._node_by_label_fragment("pages/order.jsp")
        dao = self._node_by_label_fragment("HibernateOrderDao")
        assert jsp.color != dao.color


# ---------------------------------------------------------------------------
# build_dot
# ---------------------------------------------------------------------------


class TestBuildDot:
    def setup_method(self):
        self.nodes, self.edges = build_graph({"actions": [ACTION_WITH_CHAIN]})
        self.dot = build_dot(self.nodes, self.edges)

    def test_contains_digraph(self):
        assert "digraph" in self.dot

    def test_contains_all_node_ids(self):
        for node in self.nodes:
            assert node.node_id in self.dot

    def test_contains_all_edges(self):
        for edge in self.edges:
            assert f"{edge.from_id} -> {edge.to_id}" in self.dot

    def test_splines_included_when_given(self):
        dot = build_dot(self.nodes, self.edges, splines="ortho")
        assert 'splines="ortho"' in dot

    def test_splines_absent_when_empty(self):
        dot = build_dot(self.nodes, self.edges, splines="")
        assert "splines" not in dot

    def test_default_rankdir_is_lr(self):
        dot = build_dot(self.nodes, self.edges)
        assert "rankdir=LR" in dot

    def test_rankdir_tb_when_specified(self):
        dot = build_dot(self.nodes, self.edges, rankdir="TB")
        assert "rankdir=TB" in dot

    def test_empty_graph_produces_valid_dot(self):
        dot = build_dot(frozenset(), frozenset())
        assert "digraph" in dot
        assert dot.strip().endswith("}")


# ---------------------------------------------------------------------------
# build_graph with jsp_includes in meta
# ---------------------------------------------------------------------------

DATA_WITH_INCLUDES = {
    "meta": {
        "jsp_includes": {
            "pages/parent.jsp": ["pages/child.jsp"],
            "pages/child.jsp": [],
        }
    },
    "actions": [
        {
            "jsp": "pages/parent.jsp",
            "el": "#{orderBean.submit}",
            "el_context": {"tag": "h:commandButton", "attribute": "action"},
            "bean": {
                "name": "orderBean",
                "class": "com.example.OrderBean",
                "scope": "session",
            },
            "entry_signature": None,
            "chains": [],
        },
        {
            "jsp": "pages/child.jsp",
            "el": "#{orderBean.submit}",
            "el_context": {"tag": "h:commandButton", "attribute": "action"},
            "bean": {
                "name": "orderBean",
                "class": "com.example.OrderBean",
                "scope": "session",
            },
            "entry_signature": None,
            "chains": [],
        },
    ],
}


class TestBuildGraphJspIncludes:
    def setup_method(self):
        self.nodes, self.edges = build_graph(DATA_WITH_INCLUDES)

    def test_include_edge_from_parent_to_child(self):
        parent_id = next(n.node_id for n in self.nodes if n.label == "pages/parent.jsp")
        child_id = next(n.node_id for n in self.nodes if n.label == "pages/child.jsp")
        assert Edge(parent_id, child_id) in self.edges

    def test_no_spurious_extra_nodes(self):
        # Only parent JSP, child JSP, and their EL nodes (2 JSP + 2 EL = 4)
        assert len(self.nodes) == 4

    def test_no_includes_in_meta_produces_no_include_edges(self):
        # DATA without meta.jsp_includes should not add extra edges
        nodes, edges = build_graph({"actions": [ACTION_WITH_CHAIN]})
        # Only jsp→el and el→hop edges; no jsp→jsp
        jsp_id = next(n.node_id for n in nodes if n.label == "pages/order.jsp")
        jsp_to_jsp = [
            e
            for e in edges
            if e.from_id == jsp_id
            and any(n.node_id == e.to_id and ".jsp" in n.label for n in nodes)
        ]
        assert jsp_to_jsp == []
