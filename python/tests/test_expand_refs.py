"""Tests for ftrace_expand_refs: ref expansion correctness."""

import copy

from ftrace_expand_refs import expand_refs


def _make_full_node(sig):
    """Helper to build a fully-expanded node."""
    return {
        "class": "com.example.Svc",
        "method": "doWork",
        "methodSignature": sig,
        "lineStart": 10,
        "lineEnd": 20,
        "sourceLineCount": 11,
        "sourceTrace": [{"line": 10, "code": "int x = 1;"}],
        "blocks": [{"id": "B0", "stmts": []}],
        "traps": [
            {"handler": "B2", "type": "RuntimeException", "coveredBlocks": ["B0"]}
        ],
        "children": [],
    }


def _make_ref_node(sig, call_site_line=5):
    return {
        "class": "com.example.Svc",
        "method": "doWork",
        "methodSignature": sig,
        "ref": True,
        "callSiteLine": call_site_line,
    }


def _index_from_nodes(*nodes):
    """Build a ref index from full nodes."""
    return {n["methodSignature"]: n for n in nodes}


class TestExpandRefs:
    def test_callsiteline_preserved_from_ref_node(self):
        """callSiteLine comes from the ref node, not the full expansion."""
        sig = "<com.example.Svc: void doWork()>"
        full = _make_full_node(sig)
        full["callSiteLine"] = 99
        ref = _make_ref_node(sig, call_site_line=42)

        index = _index_from_nodes(full)
        expanded = expand_refs(ref, index, frozenset())
        assert expanded["callSiteLine"] == 42

    def test_children_recursively_expanded(self):
        """Children of the full node should also have their refs expanded."""
        parent_sig = "<com.example.Svc: void parent()>"
        child_sig = "<com.example.Svc: void child()>"

        child_full = _make_full_node(child_sig)
        child_ref = _make_ref_node(child_sig, call_site_line=15)

        parent_full = _make_full_node(parent_sig)
        parent_full["children"] = [child_ref]

        parent_ref = _make_ref_node(parent_sig, call_site_line=1)

        index = _index_from_nodes(parent_full, child_full)
        expanded = expand_refs(parent_ref, index, frozenset())
        assert len(expanded["children"]) == 1
        assert expanded["children"][0]["callSiteLine"] == 15
        assert expanded["children"][0]["blocks"] == child_full["blocks"]

    def test_ref_flag_removed(self):
        """The expanded node must not carry the 'ref' flag."""
        sig = "<com.example.Svc: void doWork()>"
        full = _make_full_node(sig)
        ref = _make_ref_node(sig)

        index = _index_from_nodes(full)
        expanded = expand_refs(ref, index, frozenset())
        assert "ref" not in expanded

    def test_cycle_detection(self):
        """If the sig is already in the path, ref should not be expanded."""
        sig = "<com.example.Svc: void doWork()>"
        ref = _make_ref_node(sig)

        index = _index_from_nodes(_make_full_node(sig))
        expanded = expand_refs(ref, index, frozenset({sig}))
        assert expanded.get("ref", False) is True

    def test_ref_not_in_index_returned_as_is(self):
        """A ref whose signature is not in the index is returned unchanged."""
        ref = _make_ref_node("<com.example.Svc: void missing()>")
        expanded = expand_refs(ref, {}, frozenset())
        assert expanded.get("ref", False) is True

    def test_non_ref_children_recursed(self):
        """Non-ref nodes with children have their children expanded."""
        child_sig = "<com.example.Svc: void child()>"
        child_full = _make_full_node(child_sig)
        child_ref = _make_ref_node(child_sig)

        parent = {
            "methodSignature": "<com.example.Svc: void parent()>",
            "children": [child_ref],
        }

        index = _index_from_nodes(child_full)
        expanded = expand_refs(parent, index, frozenset())
        assert "ref" not in expanded["children"][0]
        assert expanded["children"][0]["blocks"] == child_full["blocks"]

    def test_does_not_mutate_input(self):
        """expand_refs must not mutate the input node or index."""
        sig = "<com.example.Svc: void doWork()>"
        full = _make_full_node(sig)
        ref = _make_ref_node(sig)
        index = _index_from_nodes(full)

        original_ref = copy.deepcopy(ref)
        original_index = copy.deepcopy(index)

        expand_refs(ref, index, frozenset())

        assert ref == original_ref
        assert index == original_index
