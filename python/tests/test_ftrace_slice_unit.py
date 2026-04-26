"""Unit tests for ftrace_slice pure functions."""

import copy

from ftrace_slice import collect_ref_signatures, index_full_tree


class TestCollectRefSignatures:
    def test_empty_node(self):
        assert collect_ref_signatures({"children": []}) == frozenset()

    def test_single_ref(self):
        node = {
            "children": [
                {"methodSignature": "<Svc: void a()>", "ref": True},
            ]
        }
        assert collect_ref_signatures(node) == frozenset({"<Svc: void a()>"})

    def test_non_ref_ignored(self):
        node = {
            "children": [
                {"methodSignature": "<Svc: void a()>"},
            ]
        }
        assert collect_ref_signatures(node) == frozenset()

    def test_nested_refs(self):
        node = {
            "methodSignature": "<Svc: void parent()>",
            "children": [
                {
                    "methodSignature": "<Svc: void child()>",
                    "children": [
                        {"methodSignature": "<Svc: void grandchild()>", "ref": True}
                    ],
                },
                {"methodSignature": "<Svc: void sibling()>", "ref": True},
            ],
        }
        assert collect_ref_signatures(node) == frozenset(
            {"<Svc: void grandchild()>", "<Svc: void sibling()>"}
        )

    def test_ref_without_signature_ignored(self):
        node = {"children": [{"ref": True}]}
        assert collect_ref_signatures(node) == frozenset()

    def test_does_not_mutate_input(self):
        node = {"children": [{"methodSignature": "<Svc: void a()>", "ref": True}]}
        original = copy.deepcopy(node)
        collect_ref_signatures(node)
        assert node == original


class TestIndexFullTree:
    def test_empty_signatures(self):
        tree = {"methodSignature": "<Svc: void a()>", "children": []}
        assert index_full_tree(tree, frozenset()) == {}

    def test_indexes_matching_signature(self):
        sig = "<Svc: void a()>"
        tree = {"methodSignature": sig, "children": []}
        result = index_full_tree(tree, frozenset({sig}))
        assert sig in result
        assert result[sig] is tree

    def test_skips_ref_nodes(self):
        sig = "<Svc: void a()>"
        tree = {"methodSignature": sig, "ref": True, "children": []}
        assert index_full_tree(tree, frozenset({sig})) == {}

    def test_skips_cycle_nodes(self):
        sig = "<Svc: void a()>"
        tree = {"methodSignature": sig, "cycle": True, "children": []}
        assert index_full_tree(tree, frozenset({sig})) == {}

    def test_skips_filtered_nodes(self):
        sig = "<Svc: void a()>"
        tree = {"methodSignature": sig, "filtered": True, "children": []}
        assert index_full_tree(tree, frozenset({sig})) == {}

    def test_first_occurrence_wins(self):
        sig = "<Svc: void a()>"
        first = {"methodSignature": sig, "children": [], "marker": "first"}
        second = {"methodSignature": sig, "children": [], "marker": "second"}
        tree = {"children": [first, second]}
        result = index_full_tree(tree, frozenset({sig}))
        assert result[sig]["marker"] == "first"

    def test_unmatched_signatures_excluded(self):
        tree = {
            "children": [
                {"methodSignature": "<Svc: void a()>", "children": []},
                {"methodSignature": "<Svc: void b()>", "children": []},
            ]
        }
        result = index_full_tree(tree, frozenset({"<Svc: void a()>"}))
        assert "<Svc: void a()>" in result
        assert "<Svc: void b()>" not in result
