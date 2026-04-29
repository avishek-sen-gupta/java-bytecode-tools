"""Integration tests for jspmap CLI orchestration."""

import json
import sys
import textwrap

import pytest

from jspmap.jspmap import run

# Synthetic fixtures — no strings from any real application

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

CALL_GRAPH = {
    "<com.example.web.OrderAction: void submit()>": [
        "<com.example.svc.OrderService: void place()>"
    ],
    "<com.example.svc.OrderService: void place()>": [
        "<com.example.dao.JdbcDao: void save()>"
    ],
    "<com.example.dao.JdbcDao: void save()>": [],
}

LAYERS = {
    "web": r"com\.example\.web",
    "service": r"com\.example\.svc",
    "dao": r"com\.example\.dao",
}


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
    layers_file = tmp_path / "layers.json"
    layers_file.write_text(json.dumps(LAYERS))
    return {
        "jsp_dir": jsp_dir,
        "faces": faces,
        "cg": cg,
        "layers": layers_file,
        "tmp": tmp_path,
    }


class TestRunEndToEnd:
    def test_output_has_meta(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        assert result["meta"]["dao_pattern"] == r"com\.example\.dao"

    def test_output_has_one_action(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        assert len(result["actions"]) == 1

    def test_action_el_and_bean_resolved(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        action = result["actions"][0]
        assert action["el"] == "#{orderAction.submit}"
        assert action["bean"]["class"] == "com.example.web.OrderAction"
        assert action["bean"]["scope"] == "session"

    def test_chain_ends_at_dao(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        chain = result["actions"][0]["chains"][0]
        assert chain[-1]["class"] == "com.example.dao.JdbcDao"
        assert chain[-1]["method"] == "save"

    def test_chain_has_all_hops(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        chain = result["actions"][0]["chains"][0]
        assert len(chain) == 3

    def test_layers_flag_annotates_hops(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
            layers_path=workspace["layers"],
        )
        chain = result["actions"][0]["chains"][0]
        layers = [h["layer"] for h in chain]
        assert layers == ["web", "service", "dao"]

    def test_unresolved_bean_gives_empty_chains(self, workspace, tmp_path):
        # JSP references a bean not in faces-config.xml
        jsp_dir = tmp_path / "j2"
        jsp_dir.mkdir()
        (jsp_dir / "page.jsp").write_text(
            '<h:commandButton action="#{unknownBean.go}" />'
        )
        result = run(
            jsps=jsp_dir,
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        action = result["actions"][0]
        assert action["bean"] is None
        assert action["chains"] == []

    def test_output_is_json_serialisable(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        serialised = json.dumps(result)
        assert json.loads(serialised) == result
