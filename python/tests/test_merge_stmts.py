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


class TestMergeSourceTrace:
    def test_merges_source_trace(self):
        from ftrace_semantic import merge_source_trace

        trace = [
            {"line": 5, "calls": ["Foo.bar"]},
            {"line": 5, "calls": ["Baz.qux"]},
            {"line": 10},
        ]
        result = merge_source_trace(trace)
        assert len(result) == 2
        assert result[0]["line"] == 5
        assert sorted(result[0]["calls"]) == ["Baz.qux", "Foo.bar"]

    def test_negative_lines_excluded(self):
        from ftrace_semantic import merge_source_trace

        trace = [{"line": -1}, {"line": 5}]
        result = merge_source_trace(trace)
        assert len(result) == 1

    def test_branch_entries_collected(self):
        from ftrace_semantic import merge_source_trace

        trace = [
            {"line": 6, "branch": "i <= 0"},
            {"line": 6, "branch": "x > 5"},
        ]
        result = merge_source_trace(trace)
        assert len(result) == 1
        assert result[0]["line"] == 6
        assert result[0]["branches"] == ["i <= 0", "x > 5"]

    def test_mixed_entry_types(self):
        from ftrace_semantic import merge_source_trace

        trace = [
            {"line": 5, "calls": ["Foo.bar"]},
            {"line": 5, "branch": "x > 0"},
            {"line": 5, "calls": ["Baz.qux"]},
        ]
        result = merge_source_trace(trace)
        assert len(result) == 1
        assert result[0]["line"] == 5
        assert sorted(result[0]["calls"]) == ["Baz.qux", "Foo.bar"]
        assert result[0]["branches"] == ["x > 0"]

    def test_does_not_mutate_input(self):
        from ftrace_semantic import merge_source_trace

        trace = [
            {"line": 5, "calls": ["Foo.bar"]},
            {"line": 5, "calls": ["Baz.qux"]},
        ]
        original = [dict(e) for e in trace]
        merge_source_trace(trace)
        assert trace == original


class TestAccumulateSourceTrace:
    def test_empty_accumulator(self):
        from ftrace_semantic import _accumulate_source_trace

        result = _accumulate_source_trace({}, {"line": 5, "calls": ["Foo.bar"]})
        assert result == {
            5: {"line": 5, "calls": ["Foo.bar"], "branches": [], "assigns": []}
        }

    def test_negative_line_returns_acc_unchanged(self):
        from ftrace_semantic import _accumulate_source_trace

        acc = {5: {"line": 5, "calls": [], "branches": [], "assigns": []}}
        result = _accumulate_source_trace(acc, {"line": -1})
        assert result is acc

    def test_deduplicates_calls(self):
        from ftrace_semantic import _accumulate_source_trace

        acc = {5: {"line": 5, "calls": ["Foo.bar"], "branches": [], "assigns": []}}
        result = _accumulate_source_trace(
            acc, {"line": 5, "calls": ["Foo.bar", "Baz.qux"]}
        )
        assert sorted(result[5]["calls"]) == ["Baz.qux", "Foo.bar"]

    def test_appends_branch(self):
        from ftrace_semantic import _accumulate_source_trace

        acc = {5: {"line": 5, "calls": [], "branches": ["x > 0"], "assigns": []}}
        result = _accumulate_source_trace(acc, {"line": 5, "branch": "y < 1"})
        assert result[5]["branches"] == ["x > 0", "y < 1"]


class TestAccumulateMerged:
    """Tests for the shared accumulator core."""

    def test_skips_negative_lines(self):
        from ftrace_semantic import _accumulate_merged

        acc: dict[int, MergedStmt] = {
            5: {"line": 5, "calls": [], "branches": [], "assigns": []}
        }
        result = _accumulate_merged(acc, -1, [], [], [])
        assert result is acc

    def test_merges_calls_by_line(self):
        from ftrace_semantic import _accumulate_merged

        acc: dict[int, MergedStmt] = {
            5: {"line": 5, "calls": ["Foo.x"], "branches": [], "assigns": []}
        }
        result = _accumulate_merged(acc, 5, ["Bar.y"], [], [])
        assert result[5]["calls"] == ["Foo.x", "Bar.y"]

    def test_merges_branches_by_line(self):
        from ftrace_semantic import _accumulate_merged

        acc: dict[int, MergedStmt] = {
            5: {"line": 5, "calls": [], "branches": ["x > 0"], "assigns": []}
        }
        result = _accumulate_merged(acc, 5, [], ["y < 1"], [])
        assert result[5]["branches"] == ["x > 0", "y < 1"]

    def test_merges_assigns_by_line(self):
        from ftrace_semantic import _accumulate_merged

        acc: dict[int, MergedStmt] = {
            5: {"line": 5, "calls": [], "branches": [], "assigns": ["x"]}
        }
        result = _accumulate_merged(acc, 5, [], [], ["y"])
        assert result[5]["assigns"] == ["x", "y"]

    def test_new_line_creates_entry(self):
        from ftrace_semantic import _accumulate_merged

        result = _accumulate_merged({}, 10, ["Foo.x"], [], ["z"])
        assert result == {
            10: {"line": 10, "calls": ["Foo.x"], "branches": [], "assigns": ["z"]}
        }

    def test_does_not_mutate_input(self):
        import copy
        from ftrace_semantic import _accumulate_merged

        acc: dict[int, MergedStmt] = {
            5: {"line": 5, "calls": ["A"], "branches": [], "assigns": []}
        }
        original = copy.deepcopy(acc)
        _accumulate_merged(acc, 5, ["B"], [], [])
        assert acc == original


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
                {"id": "B0", "stmts": [{"line": 5}]},
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
            "blocks": [{"id": "B0", "stmts": [{"line": 5}]}],
            "traps": [],
            "children": [
                {
                    "class": "Svc",
                    "method": "inner",
                    "blocks": [{"id": "B0", "stmts": [{"line": 10}]}],
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
            "blocks": [{"id": "B0", "stmts": [{"line": 5}]}],
            "traps": [],
            "children": [],
        }
        original = copy.deepcopy(tree)
        merge_stmts_pass(tree)
        assert tree == original


class TestMergeStmtsPassSourceTrace:
    def test_source_trace_fallback(self):
        from ftrace_semantic import merge_stmts_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "sourceTrace": [
                {"line": 5, "calls": ["Foo.bar"]},
                {"line": 10},
            ],
            "children": [],
        }
        result = merge_stmts_pass(tree)
        assert "metadata" in result
        assert "mergedSourceTrace" in result["metadata"]
        assert len(result["metadata"]["mergedSourceTrace"]) == 2
