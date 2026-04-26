"""Tests for ftrace_slice expand_refs: ref expansion correctness."""

from ftrace_slice import expand_refs, index_full_tree


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
        "blocks": [{"id": "B0", "stmts": [], "successors": ["B1"]}],
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


class TestExpandRefs:
    def test_callsiteline_preserved_from_ref_node(self):
        """callSiteLine comes from the ref node, not the full expansion."""
        sig = "<com.example.Svc: void doWork()>"
        full = _make_full_node(sig)
        full["callSiteLine"] = 99
        ref = _make_ref_node(sig, call_site_line=42)

        index = {}
        index_full_tree(full, index)

        expanded = expand_refs(ref, index, set())
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

        index = {}
        index_full_tree(parent_full, index)
        index_full_tree(child_full, index)

        expanded = expand_refs(parent_ref, index, set())
        assert len(expanded["children"]) == 1
        assert expanded["children"][0]["callSiteLine"] == 15
        assert expanded["children"][0]["blocks"] == child_full["blocks"]

    def test_ref_flag_removed(self):
        """The expanded node must not carry the 'ref' flag."""
        sig = "<com.example.Svc: void doWork()>"
        full = _make_full_node(sig)
        ref = _make_ref_node(sig)

        index = {}
        index_full_tree(full, index)

        expanded = expand_refs(ref, index, set())
        assert "ref" not in expanded or not expanded["ref"]

    def test_cycle_detection_still_works(self):
        """If the sig is already in the path, ref should not be expanded."""
        sig = "<com.example.Svc: void doWork()>"
        full = _make_full_node(sig)
        ref = _make_ref_node(sig)

        index = {}
        index_full_tree(full, index)

        expanded = expand_refs(ref, index, {sig})
        assert expanded.get("ref") is True, "should remain a ref when cycle detected"
