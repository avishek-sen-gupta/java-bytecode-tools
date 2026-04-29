"""Tests for jspmap --recurse: include-path extraction and transitive JSP collection."""

import json
import textwrap

import pytest

from jspmap.jspmap import (
    _collect_jsp_includes,
    _collect_jsp_set,
    _extract_include_paths,
    _resolve_includes,
    run,
)

# ---------------------------------------------------------------------------
# _extract_include_paths
# ---------------------------------------------------------------------------


class TestExtractIncludePaths:
    def test_jsp_include_page(self):
        content = '<jsp:include page="shared/header.jsp" />'
        assert "shared/header.jsp" in _extract_include_paths(content)

    def test_directive_include(self):
        content = "<%@ include file='fragments/nav.jsp' %>"
        assert "fragments/nav.jsp" in _extract_include_paths(content)

    def test_directive_include_double_quote(self):
        content = '<%@ include file="fragments/footer.jsp" %>'
        assert "fragments/footer.jsp" in _extract_include_paths(content)

    def test_ui_include_src(self):
        content = '<ui:include src="components/panel.xhtml" />'
        assert "components/panel.xhtml" in _extract_include_paths(content)

    def test_c_import_url(self):
        content = '<c:import url="shared/sidebar.jsp" />'
        assert "shared/sidebar.jsp" in _extract_include_paths(content)

    def test_el_valued_page_skipped(self):
        content = '<jsp:include page="#{bean.page}" />'
        assert _extract_include_paths(content) == []

    def test_el_valued_src_skipped(self):
        content = '<ui:include src="${bean.template}" />'
        assert _extract_include_paths(content) == []

    def test_external_url_in_c_import_included_raw(self):
        # _extract_include_paths is dumb; filtering external URLs happens in _resolve_includes
        content = '<c:import url="http://example.com/fragment" />'
        paths = _extract_include_paths(content)
        assert "http://example.com/fragment" in paths

    def test_no_includes_returns_empty(self):
        content = "<html><body>Hello</body></html>"
        assert _extract_include_paths(content) == []

    def test_multiple_includes_all_returned(self):
        content = textwrap.dedent("""\
            <jsp:include page="header.jsp" />
            <%@ include file="footer.jsp" %>
            <ui:include src="sidebar.xhtml" />
        """)
        paths = _extract_include_paths(content)
        assert "header.jsp" in paths
        assert "footer.jsp" in paths
        assert "sidebar.xhtml" in paths


# ---------------------------------------------------------------------------
# _resolve_includes
# ---------------------------------------------------------------------------


class TestResolveIncludes:
    def test_relative_path_resolved_from_current_jsp(self, tmp_path):
        (tmp_path / "pages" / "sm").mkdir(parents=True)
        (tmp_path / "pages" / "shared").mkdir(parents=True)
        (tmp_path / "pages" / "shared" / "header.jsp").touch()
        result = _resolve_includes(
            tmp_path, "pages/sm/close_job.jsp", ["../shared/header.jsp"]
        )
        assert "pages/shared/header.jsp" in result

    def test_absolute_path_relative_to_jsps_root(self, tmp_path):
        (tmp_path / "common").mkdir()
        (tmp_path / "common" / "nav.jsp").touch()
        result = _resolve_includes(tmp_path, "pages/foo.jsp", ["/common/nav.jsp"])
        assert "common/nav.jsp" in result

    def test_simple_sibling_resolved(self, tmp_path):
        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "nav.jsp").touch()
        result = _resolve_includes(tmp_path, "pages/main.jsp", ["nav.jsp"])
        assert "pages/nav.jsp" in result

    def test_outside_jsps_root_skipped(self, tmp_path):
        result = _resolve_includes(tmp_path, "pages/foo.jsp", ["../../etc/passwd"])
        assert result == []

    def test_http_url_skipped(self, tmp_path):
        result = _resolve_includes(
            tmp_path, "pages/foo.jsp", ["http://example.com/x.jsp"]
        )
        assert result == []

    def test_nonexistent_file_skipped(self, tmp_path):
        result = _resolve_includes(tmp_path, "pages/foo.jsp", ["pages/ghost.jsp"])
        assert result == []


# ---------------------------------------------------------------------------
# _collect_jsp_set
# ---------------------------------------------------------------------------


class TestCollectJspSet:
    def test_single_jsp_no_includes(self, tmp_path):
        (tmp_path / "main.jsp").write_text("<html/>")
        result = _collect_jsp_set(tmp_path, "main.jsp")
        assert result == frozenset(["main.jsp"])

    def test_follows_direct_include(self, tmp_path):
        (tmp_path / "main.jsp").write_text('<jsp:include page="child.jsp" />')
        (tmp_path / "child.jsp").write_text("<html/>")
        result = _collect_jsp_set(tmp_path, "main.jsp")
        assert result == frozenset(["main.jsp", "child.jsp"])

    def test_follows_transitive_includes(self, tmp_path):
        (tmp_path / "main.jsp").write_text('<jsp:include page="level1.jsp" />')
        (tmp_path / "level1.jsp").write_text('<jsp:include page="level2.jsp" />')
        (tmp_path / "level2.jsp").write_text("<html/>")
        result = _collect_jsp_set(tmp_path, "main.jsp")
        assert result == frozenset(["main.jsp", "level1.jsp", "level2.jsp"])

    def test_cycle_detection_no_infinite_loop(self, tmp_path):
        (tmp_path / "a.jsp").write_text('<jsp:include page="b.jsp" />')
        (tmp_path / "b.jsp").write_text('<jsp:include page="a.jsp" />')
        result = _collect_jsp_set(tmp_path, "a.jsp")
        assert result == frozenset(["a.jsp", "b.jsp"])

    def test_missing_included_file_skipped_gracefully(self, tmp_path):
        (tmp_path / "main.jsp").write_text('<jsp:include page="ghost.jsp" />')
        result = _collect_jsp_set(tmp_path, "main.jsp")
        assert result == frozenset(["main.jsp"])

    def test_shared_child_not_duplicated(self, tmp_path):
        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "a.jsp").write_text('<jsp:include page="shared.jsp" />')
        (tmp_path / "pages" / "shared.jsp").write_text("<html/>")
        result = _collect_jsp_set(tmp_path / "pages", "a.jsp")
        assert result == frozenset(["a.jsp", "shared.jsp"])


# ---------------------------------------------------------------------------
# run() integration with recurse=True
# ---------------------------------------------------------------------------

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
        "<com.example.dao.JdbcDao: void save()>"
    ],
    "<com.example.dao.JdbcDao: void save()>": [],
}


@pytest.fixture()
def workspace(tmp_path):
    jsp_dir = tmp_path / "jsps"
    jsp_dir.mkdir()
    faces = tmp_path / "faces-config.xml"
    faces.write_text(FACES_CONFIG)
    cg = tmp_path / "callgraph.json"
    cg.write_text(json.dumps(CALL_GRAPH))
    return {"jsp_dir": jsp_dir, "faces": faces, "cg": cg}


class TestRunRecurse:
    def test_recurse_includes_child_jsp_actions(self, workspace):
        jsp_dir = workspace["jsp_dir"]
        (jsp_dir / "main.jsp").write_text('<jsp:include page="child.jsp" />')
        (jsp_dir / "child.jsp").write_text(
            '<h:commandButton action="#{orderAction.submit}" />'
        )
        result = run(
            jsps=jsp_dir,
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
            jsp_filter="main.jsp",
            recurse=True,
        )
        jsps_in_result = {a["jsp"] for a in result["actions"]}
        assert "child.jsp" in jsps_in_result

    def test_recurse_false_excludes_child(self, workspace):
        jsp_dir = workspace["jsp_dir"]
        (jsp_dir / "main.jsp").write_text('<jsp:include page="child.jsp" />')
        (jsp_dir / "child.jsp").write_text(
            '<h:commandButton action="#{orderAction.submit}" />'
        )
        result = run(
            jsps=jsp_dir,
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
            jsp_filter="main.jsp",
            recurse=False,
        )
        jsps_in_result = {a["jsp"] for a in result["actions"]}
        assert "child.jsp" not in jsps_in_result

    def test_recurse_meta_includes_jsp_set(self, workspace):
        jsp_dir = workspace["jsp_dir"]
        (jsp_dir / "main.jsp").write_text('<jsp:include page="child.jsp" />')
        (jsp_dir / "child.jsp").write_text("<html/>")
        result = run(
            jsps=jsp_dir,
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
            jsp_filter="main.jsp",
            recurse=True,
        )
        assert "jsp_set" in result["meta"]
        assert "main.jsp" in result["meta"]["jsp_set"]
        assert "child.jsp" in result["meta"]["jsp_set"]


# ---------------------------------------------------------------------------
# _collect_jsp_includes
# ---------------------------------------------------------------------------


class TestCollectJspIncludes:
    def test_direct_include_recorded(self, tmp_path):
        (tmp_path / "main.jsp").write_text('<jsp:include page="child.jsp" />')
        (tmp_path / "child.jsp").write_text("<html/>")
        result = _collect_jsp_includes(tmp_path, frozenset(["main.jsp", "child.jsp"]))
        assert "child.jsp" in result["main.jsp"]

    def test_leaf_has_empty_children(self, tmp_path):
        (tmp_path / "main.jsp").write_text('<jsp:include page="child.jsp" />')
        (tmp_path / "child.jsp").write_text("<html/>")
        result = _collect_jsp_includes(tmp_path, frozenset(["main.jsp", "child.jsp"]))
        assert result["child.jsp"] == []

    def test_include_outside_set_not_recorded(self, tmp_path):
        # child2.jsp exists but is NOT in the jsp_set
        (tmp_path / "main.jsp").write_text(
            '<jsp:include page="child.jsp" /><jsp:include page="child2.jsp" />'
        )
        (tmp_path / "child.jsp").write_text("<html/>")
        (tmp_path / "child2.jsp").write_text("<html/>")
        result = _collect_jsp_includes(tmp_path, frozenset(["main.jsp", "child.jsp"]))
        assert "child2.jsp" not in result.get("main.jsp", [])

    def test_all_jsps_in_set_have_key(self, tmp_path):
        (tmp_path / "main.jsp").write_text('<jsp:include page="child.jsp" />')
        (tmp_path / "child.jsp").write_text("<html/>")
        result = _collect_jsp_includes(tmp_path, frozenset(["main.jsp", "child.jsp"]))
        assert set(result.keys()) == {"main.jsp", "child.jsp"}

    def test_does_not_mutate_input(self, tmp_path):
        (tmp_path / "main.jsp").write_text('<jsp:include page="child.jsp" />')
        (tmp_path / "child.jsp").write_text("<html/>")
        jsp_set = frozenset(["main.jsp", "child.jsp"])
        _collect_jsp_includes(tmp_path, jsp_set)
        assert jsp_set == frozenset(["main.jsp", "child.jsp"])


# ---------------------------------------------------------------------------
# run() integration: jsp_includes in meta
# ---------------------------------------------------------------------------


class TestRunRecurseIncludes:
    def test_meta_contains_jsp_includes(self, workspace):
        jsp_dir = workspace["jsp_dir"]
        (jsp_dir / "main.jsp").write_text('<jsp:include page="child.jsp" />')
        (jsp_dir / "child.jsp").write_text("<html/>")
        result = run(
            jsps=jsp_dir,
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
            jsp_filter="main.jsp",
            recurse=True,
        )
        assert "jsp_includes" in result["meta"]
        assert "child.jsp" in result["meta"]["jsp_includes"]["main.jsp"]

    def test_meta_jsp_includes_absent_without_recurse(self, workspace):
        jsp_dir = workspace["jsp_dir"]
        (jsp_dir / "main.jsp").write_text('<jsp:include page="child.jsp" />')
        (jsp_dir / "child.jsp").write_text("<html/>")
        result = run(
            jsps=jsp_dir,
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
            jsp_filter="main.jsp",
            recurse=False,
        )
        assert "jsp_includes" not in result["meta"]
