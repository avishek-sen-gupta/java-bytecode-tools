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

        assert render_tree(_node("com.example.Svc", "handle")) == ["Svc.handle"]

    def test_root_with_one_child(self):
        from calltree_print import render_tree

        node = _node(
            "com.example.Svc", "handle", children=[_node("com.example.Dao", "save")]
        )
        assert render_tree(node) == ["Svc.handle", "└── Dao.save"]

    def test_multiple_children_last_uses_corner(self):
        from calltree_print import render_tree

        node = _node(
            "com.example.Svc",
            "handle",
            children=[_node("com.example.A", "foo"), _node("com.example.B", "bar")],
        )
        assert render_tree(node) == ["Svc.handle", "├── A.foo", "└── B.bar"]

    def test_grandchildren_correct_prefix(self):
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
        assert render_tree(node) == [
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
                _node("com.example.A", "foo", children=[_node("com.example.B", "bar")])
            ],
        )
        assert render_tree(node) == ["Svc.handle", "└── A.foo", "    └── B.bar"]

    def test_ref_node_shows_marker_no_children(self):
        from calltree_print import render_tree

        node = _node(
            "com.example.Svc",
            "handle",
            children=[_node("com.example.Dao", "save", ref=True)],
        )
        assert render_tree(node) == ["Svc.handle", "└── Dao.save [ref]"]

    def test_cycle_node_shows_marker(self):
        from calltree_print import render_tree

        node = _node(
            "com.example.Svc",
            "handle",
            children=[_node("com.example.Svc", "handle", cycle=True)],
        )
        assert render_tree(node) == ["Svc.handle", "└── Svc.handle [↻]"]

    def test_line_range_shown(self):
        from calltree_print import render_tree

        assert render_tree(
            _node("com.example.Svc", "handle", lineStart=17, lineEnd=23)
        ) == ["Svc.handle:17-23"]

    def test_single_line_method(self):
        from calltree_print import render_tree

        assert render_tree(
            _node("com.example.Svc", "handle", lineStart=33, lineEnd=33)
        ) == ["Svc.handle:33"]

    def test_child_line_range(self):
        from calltree_print import render_tree

        node = _node(
            "com.example.Svc",
            "handle",
            children=[_node("com.example.Dao", "save", lineStart=5, lineEnd=7)],
        )
        assert render_tree(node) == ["Svc.handle", "└── Dao.save:5-7"]

    def test_does_not_mutate_input(self):
        from calltree_print import render_tree

        child = _node("com.example.Dao", "save")
        node = _node("com.example.Svc", "handle", children=[child])
        original = list(node["children"])
        render_tree(node)
        assert node["children"] == original
