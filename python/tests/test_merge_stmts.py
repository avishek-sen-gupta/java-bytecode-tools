"""Tests for pass 1: merge_stmts."""

from ftrace_types import MergedStmt, RawBlock


class TestMergeBlockStmts:
    """Unit tests for the per-block stmt merging function."""

    def test_single_stmt(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [{"line": 5}]
        result: list[MergedStmt] = merge_block_stmts(stmts)
        assert result == [{"line": 5, "calls": [], "branches": [], "assigns": []}]

    def test_multiple_stmts_same_line_merges_calls(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [
            {"line": 9, "call": "Foo.bar"},
            {"line": 9, "call": "Baz.qux"},
            {"line": 9},
        ]
        result = merge_block_stmts(stmts)
        assert len(result) == 1
        assert result[0]["line"] == 9
        assert result[0]["calls"] == ["Foo.bar", "Baz.qux"]

    def test_negative_lines_excluded(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [{"line": -1}, {"line": 5}]
        result = merge_block_stmts(stmts)
        assert len(result) == 1
        assert result[0]["line"] == 5

    def test_branches_collected(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [{"line": 6, "branch": "i <= 0"}]
        result = merge_block_stmts(stmts)
        assert result[0]["branches"] == ["i <= 0"]

    def test_assigns_collected(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [{"line": 7, "assign": "x = 5"}]
        result = merge_block_stmts(stmts)
        assert result[0]["assigns"] == ["x = 5"]

    def test_sorted_by_line(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [{"line": 10}, {"line": 3}, {"line": 7}]
        result = merge_block_stmts(stmts)
        assert [m["line"] for m in result] == [3, 7, 10]

    def test_empty_stmts(self):
        from ftrace_semantic import merge_block_stmts

        assert merge_block_stmts([]) == []


class TestMergeStmtsPass:
    """Tests for the full tree-walking pass."""

    def test_adds_merged_stmts_to_blocks(self):
        from ftrace_semantic import merge_stmts_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [
                {
                    "id": "B0",
                    "stmts": [{"line": 5}, {"line": 5, "call": "Foo.x"}],
                    "successors": [],
                },
            ],
            "traps": [],
            "children": [],
        }
        result = merge_stmts_pass(tree)
        assert result is not tree  # new dict, not mutated
        assert "mergedStmts" in result["blocks"][0]
        assert result["blocks"][0]["mergedStmts"][0]["calls"] == ["Foo.x"]

    def test_preserves_raw_stmts(self):
        from ftrace_semantic import merge_stmts_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [
                {"id": "B0", "stmts": [{"line": 5}], "successors": []},
            ],
            "traps": [],
            "children": [],
        }
        result = merge_stmts_pass(tree)
        assert "stmts" in result["blocks"][0]

    def test_recurses_into_children(self):
        from ftrace_semantic import merge_stmts_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0", "stmts": [{"line": 5}], "successors": []}],
            "traps": [],
            "children": [
                {
                    "class": "Svc",
                    "method": "inner",
                    "blocks": [{"id": "B0", "stmts": [{"line": 10}], "successors": []}],
                    "traps": [],
                    "children": [],
                }
            ],
        }
        result = merge_stmts_pass(tree)
        assert "mergedStmts" in result["children"][0]["blocks"][0]

    def test_leaf_nodes_pass_through(self):
        from ftrace_semantic import merge_stmts_pass

        tree = {"class": "Svc", "method": "run", "ref": True, "methodSignature": "sig"}
        result = merge_stmts_pass(tree)
        assert result == tree
        assert result is not tree  # still a copy

    def test_does_not_mutate_input(self):
        from ftrace_semantic import merge_stmts_pass
        import copy

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0", "stmts": [{"line": 5}], "successors": []}],
            "traps": [],
            "children": [],
        }
        original = copy.deepcopy(tree)
        merge_stmts_pass(tree)
        assert tree == original
