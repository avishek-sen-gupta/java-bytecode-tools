"""Integration tests for jspmap CLI — flat {nodes, calls, metadata} schema."""

import json
import textwrap

import pytest

from jspmap.jspmap import run

FACES_CONFIG = textwrap.dedent("""\
    <?xml version="1.0"?>
    <faces-config>
      <managed-bean>
        <managed-bean-name>orderAction</managed-bean-name>
        <managed-bean-class>com.example.web.OrderAction</managed-bean-class>
        <managed-bean-scope>session</managed-bean-scope>
      </managed-bean>
    </faces-config>
""")

# Raw callees dict — jspmap reads cg_data.get("callees", cg_data) so this works
CALL_GRAPH = {
    "<com.example.web.OrderAction: void submit()>": [
        "<com.example.svc.OrderService: void place()>"
    ],
    "<com.example.svc.OrderService: void place()>": [
        "<com.example.dao.JdbcDao: void save()>"
    ],
    "<com.example.dao.JdbcDao: void save()>": [],
}

JSP_KEY = "jsp:/order.jsp"
EL_KEY = "el:/order.jsp##{orderAction.submit}"
ENTRY_SIG = "<com.example.web.OrderAction: void submit()>"
SVC_SIG = "<com.example.svc.OrderService: void place()>"
DAO_SIG = "<com.example.dao.JdbcDao: void save()>"


@pytest.fixture()
def workspace(tmp_path):
    jsp_dir = tmp_path / "jsps"
    jsp_dir.mkdir()
    (jsp_dir / "order.jsp").write_text(
        '<h:commandButton action="#{orderAction.submit}" />'
    )
    faces = tmp_path / "faces-config.xml"
    faces.write_text(FACES_CONFIG)
    cg = tmp_path / "callgraph.json"
    cg.write_text(json.dumps(CALL_GRAPH))
    return {"jsp_dir": jsp_dir, "faces": faces, "cg": cg, "tmp": tmp_path}


@pytest.fixture()
def result(workspace):
    return run(
        jsps=workspace["jsp_dir"],
        faces_config=workspace["faces"],
        call_graph_path=workspace["cg"],
    )


class TestFlatSchemaStructure:
    def test_output_has_nodes_calls_metadata(self, result):
        assert "nodes" in result
        assert "calls" in result
        assert "metadata" in result

    def test_no_legacy_meta_or_actions_keys(self, result):
        assert "meta" not in result
        assert "actions" not in result

    def test_metadata_tool_is_jspmap(self, result):
        assert result["metadata"]["tool"] == "jspmap"

    def test_metadata_has_required_keys(self, workspace, result):
        meta = result["metadata"]
        assert "jsps_root" in meta
        assert "faces_config" in meta
        assert "call_graph" in meta

    def test_output_is_json_serialisable(self, result):
        serialised = json.dumps(result)
        assert json.loads(serialised) == result


class TestJspNode:
    def test_jsp_node_present(self, result):
        assert JSP_KEY in result["nodes"]

    def test_jsp_node_type(self, result):
        assert result["nodes"][JSP_KEY]["node_type"] == "jsp"

    def test_jsp_node_method_signature(self, result):
        assert result["nodes"][JSP_KEY]["methodSignature"] == JSP_KEY

    def test_jsp_node_method_is_empty(self, result):
        assert result["nodes"][JSP_KEY]["method"] == ""


class TestElNode:
    def test_el_node_present(self, result):
        assert EL_KEY in result["nodes"]

    def test_el_node_type(self, result):
        assert result["nodes"][EL_KEY]["node_type"] == "el_expression"

    def test_el_node_has_expression_field(self, result):
        assert result["nodes"][EL_KEY]["expression"] == "#{orderAction.submit}"

    def test_el_node_method_signature(self, result):
        assert result["nodes"][EL_KEY]["methodSignature"] == EL_KEY


class TestJavaNodes:
    def test_entry_sig_node_present(self, result):
        assert ENTRY_SIG in result["nodes"]

    def test_entry_sig_node_type_java_method(self, result):
        assert result["nodes"][ENTRY_SIG]["node_type"] == "java_method"

    def test_dao_node_present(self, result):
        assert DAO_SIG in result["nodes"]

    def test_all_java_nodes_have_node_type(self, result):
        java_sigs = [ENTRY_SIG, SVC_SIG, DAO_SIG]
        for sig in java_sigs:
            assert result["nodes"][sig]["node_type"] == "java_method"


class TestCallEdges:
    def _edge(self, result, from_key, to_key):
        return next(
            (c for c in result["calls"] if c["from"] == from_key and c["to"] == to_key),
            None,
        )

    def test_jsp_to_el_edge_present(self, result):
        assert self._edge(result, JSP_KEY, EL_KEY) is not None

    def test_jsp_to_el_edge_type(self, result):
        edge = self._edge(result, JSP_KEY, EL_KEY)
        assert edge is not None
        assert edge["edge_info"] == {"edge_type": "el_call"}

    def test_el_to_entry_edge_present(self, result):
        assert self._edge(result, EL_KEY, ENTRY_SIG) is not None

    def test_el_to_entry_edge_type(self, result):
        edge = self._edge(result, EL_KEY, ENTRY_SIG)
        assert edge is not None
        assert edge["edge_info"] == {"edge_type": "method_call"}

    def test_java_java_edges_have_empty_edge_info(self, result):
        java_edges = [
            c
            for c in result["calls"]
            if c["from"] not in (JSP_KEY, EL_KEY)
            and c["to"] not in (JSP_KEY, EL_KEY)
            and not c.get("filtered")
            and not c.get("cycle")
        ]
        assert java_edges, "expected at least one Java→Java edge"
        for edge in java_edges:
            assert edge["edge_info"] == {}

    def test_all_edges_have_edge_info_key(self, result):
        for edge in result["calls"]:
            assert "edge_info" in edge, f"missing edge_info on: {edge}"


class TestNewCallgraphFormat:
    def test_callees_subkey_format_works(self, workspace, tmp_path):
        cg = tmp_path / "cg_new.json"
        cg.write_text(
            json.dumps({"callees": CALL_GRAPH, "callsites": {}, "methodLines": {}})
        )
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=cg,
        )
        assert ENTRY_SIG in result["nodes"]
        assert DAO_SIG in result["nodes"]


class TestUnresolvedBean:
    def test_unresolved_bean_produces_only_jsp_node(self, workspace, tmp_path):
        jsp_dir = tmp_path / "j2"
        jsp_dir.mkdir()
        (jsp_dir / "page.jsp").write_text(
            '<h:commandButton action="#{unknownBean.go}" />'
        )
        result = run(
            jsps=jsp_dir,
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
        )
        # Should have a JSP node for the page but no EL or Java nodes
        assert "jsp:/page.jsp" in result["nodes"]
        assert not any(k.startswith("el:") for k in result["nodes"])
        assert not any(k.startswith("<") for k in result["nodes"])


class TestPatternFiltering:
    def test_pattern_filters_out_of_scope_nodes(self, workspace):
        # Only include web layer — svc and dao should be filtered edges, not nodes
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            pattern=r"com\.example\.web",
        )
        assert ENTRY_SIG in result["nodes"]
        assert SVC_SIG not in result["nodes"]
        assert DAO_SIG not in result["nodes"]
