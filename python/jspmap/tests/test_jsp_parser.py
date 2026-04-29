"""Tests for jsp_parser — EL tokenizer, classifier, and DOM walk."""

from jspmap.jsp_parser import tokenize_el


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
