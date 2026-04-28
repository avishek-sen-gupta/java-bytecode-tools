"""Unit tests for ftrace_slice pure functions."""

import copy

from ftrace_slice import (
    collect_ref_signatures,
    find_subtree,
    index_full_tree,
    matches,
    prune_to_target,
)


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

    def test_does_not_mutate_input(self):
        sig = "<Svc: void a()>"
        tree = {"methodSignature": sig, "children": []}
        original = copy.deepcopy(tree)
        index_full_tree(tree, frozenset({sig}))
        assert tree == original

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


class TestMatches:
    def _node(self, class_name: str, line_start: int = 0, line_end: int = 0):
        return {
            "class": class_name,
            "lineStart": line_start,
            "lineEnd": line_end,
            "children": [],
        }

    def test_matches_by_class_only(self):
        node = self._node("com.example.Service")
        assert matches(node, "com.example.Service", 0) is True

    def test_rejects_class_mismatch(self):
        node = self._node("com.example.Service")
        assert matches(node, "com.example.Other", 0) is False

    def test_matches_line_within_range(self):
        node = self._node("com.example.Service", line_start=10, line_end=50)
        assert matches(node, "com.example.Service", 30) is True

    def test_matches_line_at_start(self):
        node = self._node("com.example.Service", line_start=10, line_end=50)
        assert matches(node, "com.example.Service", 10) is True

    def test_matches_line_at_end(self):
        node = self._node("com.example.Service", line_start=10, line_end=50)
        assert matches(node, "com.example.Service", 50) is True

    def test_rejects_line_out_of_range(self):
        node = self._node("com.example.Service", line_start=10, line_end=50)
        assert matches(node, "com.example.Service", 60) is False

    def test_rejects_line_before_range(self):
        node = self._node("com.example.Service", line_start=10, line_end=50)
        assert matches(node, "com.example.Service", 5) is False

    def test_missing_line_fields_no_match_when_line_given(self):
        node = {"class": "com.example.Service", "children": []}
        assert matches(node, "com.example.Service", 42) is False

    def test_line_zero_skips_range_check(self):
        node = {"class": "com.example.Service", "children": []}
        assert matches(node, "com.example.Service", 0) is True


class TestFindSubtree:
    def test_finds_node_at_root(self):
        node = {"class": "com.example.A", "lineStart": 1, "lineEnd": 10, "children": []}
        result = find_subtree(node, "com.example.A", 0)
        assert result == [node]

    def test_finds_node_in_children(self):
        child = {
            "class": "com.example.B",
            "lineStart": 5,
            "lineEnd": 20,
            "children": [],
        }
        root = {"class": "com.example.A", "children": [child]}
        result = find_subtree(root, "com.example.B", 0)
        assert result == [child]

    def test_finds_node_in_grandchildren(self):
        grandchild = {
            "class": "com.example.C",
            "lineStart": 1,
            "lineEnd": 5,
            "children": [],
        }
        child = {"class": "com.example.B", "children": [grandchild]}
        root = {"class": "com.example.A", "children": [child]}
        result = find_subtree(root, "com.example.C", 0)
        assert result == [grandchild]

    def test_returns_empty_when_not_found(self):
        root = {"class": "com.example.A", "children": []}
        assert find_subtree(root, "com.example.Z", 0) == []

    def test_returns_first_match_dfs_order(self):
        first = {
            "class": "com.example.B",
            "lineStart": 1,
            "lineEnd": 10,
            "children": [],
            "marker": "first",
        }
        second = {
            "class": "com.example.B",
            "lineStart": 1,
            "lineEnd": 10,
            "children": [],
            "marker": "second",
        }
        root = {"class": "com.example.A", "children": [first, second]}
        result = find_subtree(root, "com.example.B", 0)
        assert result[0].get("marker") == "first"

    def test_does_not_mutate_input(self):
        node = {
            "class": "com.example.A",
            "children": [{"class": "com.example.B", "children": []}],
        }
        original = copy.deepcopy(node)
        find_subtree(node, "com.example.B", 0)
        assert node == original


class TestPruneToTarget:
    def test_returns_empty_when_target_not_reachable(self):
        root = {"class": "com.example.A", "children": []}
        assert prune_to_target(root, "com.example.Z", 0) == []

    def test_returns_node_with_no_children_when_node_is_target(self):
        node = {
            "class": "com.example.A",
            "lineStart": 1,
            "lineEnd": 10,
            "children": [{"class": "com.example.B", "children": []}],
        }
        result = prune_to_target(node, "com.example.A", 0)
        assert len(result) == 1
        assert result[0]["children"] == []

    def test_returns_single_path_to_target(self):
        target = {
            "class": "com.example.C",
            "lineStart": 1,
            "lineEnd": 5,
            "children": [],
        }
        branch = {"class": "com.example.B", "children": [target]}
        sibling = {"class": "com.example.X", "children": []}
        root = {"class": "com.example.A", "children": [branch, sibling]}
        result = prune_to_target(root, "com.example.C", 0)
        assert len(result) == 1
        pruned = result[0]
        assert len(pruned["children"]) == 1
        assert pruned["children"][0]["class"] == "com.example.B"
        assert pruned["children"][0]["children"][0]["class"] == "com.example.C"

    def test_preserves_both_paths_when_two_routes_reach_target(self):
        target1 = {
            "class": "com.example.C",
            "lineStart": 1,
            "lineEnd": 5,
            "children": [],
        }
        target2 = {
            "class": "com.example.C",
            "lineStart": 1,
            "lineEnd": 5,
            "children": [],
        }
        branch1 = {"class": "com.example.B1", "children": [target1]}
        branch2 = {"class": "com.example.B2", "children": [target2]}
        dead_end = {"class": "com.example.X", "children": []}
        root = {"class": "com.example.A", "children": [branch1, branch2, dead_end]}
        result = prune_to_target(root, "com.example.C", 0)
        assert len(result) == 1
        pruned = result[0]
        assert len(pruned["children"]) == 2
        child_classes = {c["class"] for c in pruned["children"]}
        assert child_classes == {"com.example.B1", "com.example.B2"}

    def test_strips_children_of_target_node(self):
        deeper = {"class": "com.example.D", "children": []}
        target = {
            "class": "com.example.C",
            "lineStart": 1,
            "lineEnd": 5,
            "children": [deeper],
        }
        root = {"class": "com.example.A", "children": [target]}
        result = prune_to_target(root, "com.example.C", 0)
        assert len(result) == 1
        target_node = result[0]["children"][0]
        assert target_node["class"] == "com.example.C"
        assert target_node["children"] == []

    def test_does_not_mutate_input(self):
        target = {
            "class": "com.example.C",
            "lineStart": 1,
            "lineEnd": 5,
            "children": [],
        }
        root = {"class": "com.example.A", "children": [target]}
        original = copy.deepcopy(root)
        prune_to_target(root, "com.example.C", 0)
        assert root == original
