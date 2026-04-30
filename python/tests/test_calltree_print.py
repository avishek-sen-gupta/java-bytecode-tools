"""Tests for calltree_print with flat {nodes, calls} schema."""

SIG_SVC = "<com.example.Svc: void handle()>"
SIG_DAO = "<com.example.Dao: void save()>"
SIG_FOO = "<com.example.A: void foo()>"
SIG_BAR = "<com.example.B: void bar()>"
SIG_BAZ = "<com.example.C: void baz()>"
SIG_QUX = "<com.example.D: void qux()>"


def _node(sig: str, cls: str, method: str) -> dict:
    return {"class": cls, "method": method, "methodSignature": sig}


NODES = {
    SIG_SVC: _node(SIG_SVC, "com.example.Svc", "handle"),
    SIG_DAO: _node(SIG_DAO, "com.example.Dao", "save"),
}


class TestRenderFlat:
    def test_single_root_no_children(self):
        from calltree_print import render_flat

        nodes = {SIG_SVC: _node(SIG_SVC, "com.example.Svc", "handle")}
        calls = []
        lines = render_flat(nodes, calls)
        assert lines == ["Svc.handle"]

    def test_root_with_one_child(self):
        from calltree_print import render_flat

        nodes = {
            SIG_SVC: _node(SIG_SVC, "com.example.Svc", "handle"),
            SIG_DAO: _node(SIG_DAO, "com.example.Dao", "save"),
        }
        calls = [{"from": SIG_SVC, "to": SIG_DAO, "callSiteLine": 42}]
        lines = render_flat(nodes, calls)
        assert lines == ["Svc.handle", "└── Dao.save:42"]

    def test_root_with_multiple_children_last_uses_corner(self):
        from calltree_print import render_flat

        nodes = {
            SIG_FOO: _node(SIG_FOO, "com.example.A", "foo"),
            SIG_BAR: _node(SIG_BAR, "com.example.B", "bar"),
            SIG_BAZ: _node(SIG_BAZ, "com.example.C", "baz"),
        }
        calls = [
            {"from": SIG_FOO, "to": SIG_BAR, "callSiteLine": 10},
            {"from": SIG_FOO, "to": SIG_BAZ, "callSiteLine": 20},
        ]
        lines = render_flat(nodes, calls)
        assert lines[0] == "A.foo"
        assert "├── B.bar:10" in lines
        assert "└── C.baz:20" in lines

    def test_cycle_edges_shown_with_marker(self):
        from calltree_print import render_flat

        nodes = {SIG_SVC: _node(SIG_SVC, "com.example.Svc", "handle")}
        calls = [{"from": SIG_SVC, "to": SIG_SVC, "cycle": True}]
        lines = render_flat(nodes, calls)
        assert any("[↻]" in line for line in lines)

    def test_no_callsite_line_no_suffix(self):
        from calltree_print import render_flat

        nodes = {SIG_SVC: _node(SIG_SVC, "com.example.Svc", "handle")}
        calls = []
        assert render_flat(nodes, calls) == ["Svc.handle"]

    def test_grandchildren_correct_prefix(self):
        from calltree_print import render_flat

        nodes = {
            SIG_SVC: _node(SIG_SVC, "com.example.Svc", "handle"),
            SIG_FOO: _node(SIG_FOO, "com.example.A", "foo"),
            SIG_BAR: _node(SIG_BAR, "com.example.B", "bar"),
            SIG_BAZ: _node(SIG_BAZ, "com.example.C", "baz"),
            SIG_QUX: _node(SIG_QUX, "com.example.D", "qux"),
        }
        calls = [
            {"from": SIG_SVC, "to": SIG_FOO},
            {"from": SIG_FOO, "to": SIG_BAR},
            {"from": SIG_FOO, "to": SIG_BAZ},
            {"from": SIG_SVC, "to": SIG_QUX},
        ]
        lines = render_flat(nodes, calls)
        assert lines[0] == "Svc.handle"
        assert "├── A.foo" in lines
        assert "│   ├── B.bar" in lines
        assert "│   └── C.baz" in lines
        assert "└── D.qux" in lines

    def test_does_not_mutate_inputs(self):
        from copy import deepcopy
        from calltree_print import render_flat

        nodes = {SIG_SVC: _node(SIG_SVC, "com.example.Svc", "handle")}
        calls = [{"from": SIG_SVC, "to": SIG_DAO, "callSiteLine": 42}]
        nodes_before = deepcopy(nodes)
        calls_before = deepcopy(calls)

        render_flat(nodes, calls)

        assert nodes == nodes_before
        assert calls == calls_before
