"""Tests for jsp_parser — EL tokenizer, classifier, and DOM walk."""

import textwrap
import os
from jspmap.jsp_parser import tokenize_el, classify_el, parse_jsps


class TestTokenizeEl:
    def test_single_hash_expression(self):
        assert tokenize_el("#{a.b}") == ["#{a.b}"]

    def test_single_dollar_expression(self):
        assert tokenize_el("${a.b}") == ["${a.b}"]

    def test_two_expressions_in_one_string(self):
        result = tokenize_el("#{a.b} and #{c.d}")
        assert result == ["#{a.b}", "#{c.d}"]

    def test_no_el_returns_empty(self):
        assert tokenize_el("plain text") == []

    def test_nested_braces_inside_expression(self):
        # #{map.get('key{1}')} — braces inside single-quoted string do not close the expression
        result = tokenize_el("#{map.get('key{1}')}")
        assert result == ["#{map.get('key{1}')}"]

    def test_double_quoted_string_with_braces(self):
        result = tokenize_el('#{map.get("k{v}")}')
        assert result == ['#{map.get("k{v}")}']

    def test_expression_embedded_in_larger_string(self):
        result = tokenize_el("prefix #{a.b} suffix")
        assert result == ["#{a.b}"]

    def test_adjacent_expressions(self):
        result = tokenize_el("#{a.b}#{c.d}")
        assert result == ["#{a.b}", "#{c.d}"]

    def test_unmatched_brace_not_included(self):
        # A lone # not followed by { should not trigger an expression
        result = tokenize_el("# not an expression")
        assert result == []

    def test_returns_list_not_generator(self):
        result = tokenize_el("#{a.b}")
        assert isinstance(result, list)


class TestClassifyEl:
    def test_simple_bean_and_member(self):
        assert classify_el("#{orderAction.submit}") == ("orderAction", "submit")

    def test_no_member_returns_empty_string(self):
        bn, mem = classify_el("#{orderAction}")
        assert bn == "orderAction"
        assert mem == ""

    def test_chained_member_returns_first_only(self):
        bn, mem = classify_el("#{a.b.c}")
        assert bn == "a"
        assert mem == "b"

    def test_dollar_expression(self):
        bn, mem = classify_el("${foo.bar}")
        assert bn == "foo"
        assert mem == "bar"

    def test_arithmetic_expression_returns_empty_bean(self):
        bn, mem = classify_el("#{1 + 2}")
        assert bn == ""
        assert mem == ""

    def test_does_not_mutate_input(self):
        expr = "#{a.b}"
        original = expr[:]
        classify_el(expr)
        assert expr == original


class TestParseJsps:
    def test_extracts_action_attribute(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        jsp_dir.mkdir()
        (jsp_dir / "test.jsp").write_text(
            '<h:commandButton action="#{orderAction.submit}" />'
        )
        result = parse_jsps(jsp_dir, ["jsp"])
        assert len(result) == 1
        action = result[0]
        assert action.el == "#{orderAction.submit}"
        assert action.tag == "h:commandbutton"  # BeautifulSoup lowercases tag names
        assert action.attribute == "action"
        assert action.bean_name == "orderAction"
        assert action.member == "submit"

    def test_extracts_text_node(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        jsp_dir.mkdir()
        (jsp_dir / "test.jsp").write_text("<p>#{userBean.name}</p>")
        result = parse_jsps(jsp_dir, ["jsp"])
        text_actions = [a for a in result if a.attribute == "_text"]
        assert len(text_actions) == 1
        assert text_actions[0].bean_name == "userBean"
        assert text_actions[0].member == "name"

    def test_no_el_produces_empty_result(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        jsp_dir.mkdir()
        (jsp_dir / "test.jsp").write_text("<html><body>Hello world</body></html>")
        result = parse_jsps(jsp_dir, ["jsp"])
        assert result == []

    def test_jsp_path_is_relative_to_root(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        sub = jsp_dir / "pages"
        sub.mkdir(parents=True)
        (sub / "order.jsp").write_text('<h:commandButton action="#{a.b}" />')
        result = parse_jsps(jsp_dir, ["jsp"])
        assert result[0].jsp == os.path.join("pages", "order.jsp")

    def test_multiple_extensions(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        jsp_dir.mkdir()
        (jsp_dir / "a.jsp").write_text('<f:view action="#{a.m}" />')
        (jsp_dir / "b.xhtml").write_text('<h:form action="#{b.m}" />')
        result = parse_jsps(jsp_dir, ["jsp", "xhtml"])
        bean_names = {a.bean_name for a in result}
        assert "a" in bean_names
        assert "b" in bean_names

    def test_does_not_mutate_input(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        jsp_dir.mkdir()
        (jsp_dir / "test.jsp").write_text('<h:commandButton action="#{a.b}" />')
        extensions = ["jsp"]
        original = extensions[:]
        parse_jsps(jsp_dir, extensions)
        assert extensions == original
