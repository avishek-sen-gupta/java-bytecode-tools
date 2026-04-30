"""Tests for calltree line-number annotation."""


def _dump_entry(sig: str, line_start: int, line_end: int) -> dict:
    return {"signature": sig, "lineStart": line_start, "lineEnd": line_end}


def _dump_file(cls: str, methods: list) -> dict:
    return {"class": cls, "methods": methods}


def _node(cls: str, method: str, sig: str | None = None, children=(), **kwargs):
    s = sig or f"<{cls}: void {method}()>"
    return {
        "class": cls,
        "method": method,
        "methodSignature": s,
        "children": list(children),
        **kwargs,
    }


class TestBuildLineIndex:
    def test_single_dump_file_two_methods(self):
        from calltree import build_line_index

        dump = _dump_file(
            "com.example.Svc",
            [
                _dump_entry("<com.example.Svc: void handle()>", 10, 20),
                _dump_entry("<com.example.Svc: void save()>", 25, 25),
            ],
        )
        idx = build_line_index([dump])
        assert idx["<com.example.Svc: void handle()>"] == {
            "lineStart": 10,
            "lineEnd": 20,
        }
        assert idx["<com.example.Svc: void save()>"] == {"lineStart": 25, "lineEnd": 25}

    def test_multiple_dump_files_merged(self):
        from calltree import build_line_index

        d1 = _dump_file("A", [_dump_entry("<A: void foo()>", 1, 3)])
        d2 = _dump_file("B", [_dump_entry("<B: void bar()>", 7, 9)])
        idx = build_line_index([d1, d2])
        assert "<A: void foo()>" in idx
        assert "<B: void bar()>" in idx

    def test_empty_input_returns_empty(self):
        from calltree import build_line_index

        assert build_line_index([]) == {}

    def test_does_not_mutate_input(self):
        from calltree import build_line_index

        dump = _dump_file("A", [_dump_entry("<A: void foo()>", 1, 3)])
        original_methods = list(dump["methods"])
        build_line_index([dump])
        assert dump["methods"] == original_methods


class TestAnnotateTree:
    def test_node_with_matching_sig_gets_lines(self):
        from calltree import annotate_tree

        node = _node("com.example.Svc", "handle")
        sig = node["methodSignature"]
        idx = {sig: {"lineStart": 10, "lineEnd": 20}}
        result = annotate_tree(node, idx)
        assert result["lineStart"] == 10
        assert result["lineEnd"] == 20

    def test_node_without_match_unchanged(self):
        from calltree import annotate_tree

        node = _node("com.example.Svc", "handle")
        result = annotate_tree(node, {})
        assert "lineStart" not in result
        assert "lineEnd" not in result

    def test_children_are_annotated_recursively(self):
        from calltree import annotate_tree

        child = _node("com.example.Dao", "save")
        parent = _node("com.example.Svc", "handle", children=[child])
        child_sig = child["methodSignature"]
        idx = {child_sig: {"lineStart": 5, "lineEnd": 7}}
        result = annotate_tree(parent, idx)
        assert result["children"][0]["lineStart"] == 5

    def test_ref_node_gets_lines(self):
        from calltree import annotate_tree

        node = _node("com.example.Dao", "save", ref=True)
        sig = node["methodSignature"]
        idx = {sig: {"lineStart": 5, "lineEnd": 7}}
        result = annotate_tree(node, idx)
        assert result["lineStart"] == 5

    def test_does_not_mutate_input(self):
        from calltree import annotate_tree

        child = _node("com.example.Dao", "save")
        parent = _node("com.example.Svc", "handle", children=[child])
        original_children = list(parent["children"])
        annotate_tree(parent, {})
        assert parent["children"] == original_children
