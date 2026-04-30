"""Tests for calltree ASCII pretty-printer."""


def _node(cls: str, method: str, children=(), **kwargs):
    return {
        "class": cls,
        "method": method,
        "methodSignature": f"<{cls}: void {method}()>",
        "children": list(children),
        **kwargs,
    }


class TestRenderTree:
    def test_single_root_no_children(self):
        from calltree_print import render_tree

        node = _node("com.example.Svc", "handle")
        assert render_tree(node) == ["Svc.handle"]

    def test_root_with_one_child(self):
        from calltree_print import render_tree

        node = _node(
            "com.example.Svc", "handle", children=[_node("com.example.Dao", "save")]
        )
        lines = render_tree(node)
        assert lines == ["Svc.handle", "└── Dao.save"]

    def test_root_with_multiple_children_last_uses_corner(self):
        from calltree_print import render_tree

        node = _node(
            "com.example.Svc",
            "handle",
            children=[
                _node("com.example.A", "foo"),
                _node("com.example.B", "bar"),
            ],
        )
        lines = render_tree(node)
        assert lines == ["Svc.handle", "├── A.foo", "└── B.bar"]

    def test_grandchildren_use_correct_prefix(self):
        from calltree_print import render_tree

        node = _node(
            "com.example.Svc",
            "handle",
            children=[
                _node(
                    "com.example.A",
                    "foo",
                    children=[
                        _node("com.example.B", "bar"),
                        _node("com.example.C", "baz"),
                    ],
                ),
                _node("com.example.D", "qux"),
            ],
        )
        lines = render_tree(node)
        assert lines == [
            "Svc.handle",
            "├── A.foo",
            "│   ├── B.bar",
            "│   └── C.baz",
            "└── D.qux",
        ]

    def test_last_child_grandchildren_use_spaces(self):
        from calltree_print import render_tree

        node = _node(
            "com.example.Svc",
            "handle",
            children=[
                _node(
                    "com.example.A",
                    "foo",
                    children=[_node("com.example.B", "bar")],
                ),
            ],
        )
        lines = render_tree(node)
        assert lines == ["Svc.handle", "└── A.foo", "    └── B.bar"]

    def test_ref_node_shows_marker_no_children(self):
        from calltree_print import render_tree

        child = _node("com.example.Dao", "save", ref=True)
        node = _node("com.example.Svc", "handle", children=[child])
        lines = render_tree(node)
        assert lines == ["Svc.handle", "└── Dao.save [ref]"]

    def test_cycle_node_shows_marker(self):
        from calltree_print import render_tree

        child = _node("com.example.Svc", "handle", cycle=True)
        node = _node("com.example.Svc", "handle", children=[child])
        lines = render_tree(node)
        assert lines == ["Svc.handle", "└── Svc.handle [↻]"]

    def test_does_not_mutate_input(self):
        from calltree_print import render_tree

        child = _node("com.example.Dao", "save")
        node = _node("com.example.Svc", "handle", children=[child])
        original_children = list(node["children"])
        render_tree(node)
        assert node["children"] == original_children

    def test_child_callsite_line_shown(self):
        from calltree_print import render_tree

        child = _node("com.example.Dao", "save", callSiteLine=42)
        node = _node("com.example.Svc", "handle", children=[child])
        lines = render_tree(node)
        assert lines == ["Svc.handle", "└── Dao.save:42"]

    def test_no_callsite_line_no_suffix(self):
        from calltree_print import render_tree

        node = _node("com.example.Svc", "handle")
        assert render_tree(node) == ["Svc.handle"]

    def test_callsite_line_with_ref_marker(self):
        from calltree_print import render_tree

        child = _node("com.example.Dao", "save", ref=True, callSiteLine=99)
        node = _node("com.example.Svc", "handle", children=[child])
        lines = render_tree(node)
        assert lines == ["Svc.handle", "└── Dao.save:99 [ref]"]
