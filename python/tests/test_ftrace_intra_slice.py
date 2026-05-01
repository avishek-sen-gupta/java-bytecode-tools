"""Unit tests for ftrace_intra_slice pure functions."""

import copy

from ftrace_intra_slice import (
    backward_reachable,
    blocks_containing_line,
    forward_reachable,
    intra_slice,
    lines_in_kept_blocks,
    slice_blocks,
    slice_children,
    slice_edges,
    slice_source_trace,
    slice_traps,
)


def _block(block_id: str, lines: list[int]) -> dict:
    return {"id": block_id, "stmts": [{"line": line} for line in lines]}


def _edge(from_block: str, to_block: str, label: str = "") -> dict:
    e = {"fromBlock": from_block, "toBlock": to_block}
    if label:
        e["label"] = label
    return e


class TestBlocksContainingLine:
    def test_returns_block_id_when_line_present(self):
        blocks = [_block("b0", [10, 11, 12])]
        assert blocks_containing_line(blocks, 11) == frozenset({"b0"})

    def test_returns_empty_when_line_absent(self):
        blocks = [_block("b0", [10, 11])]
        assert blocks_containing_line(blocks, 99) == frozenset()

    def test_returns_multiple_blocks_for_same_line(self):
        blocks = [_block("b0", [10]), _block("b1", [10])]
        assert blocks_containing_line(blocks, 10) == frozenset({"b0", "b1"})

    def test_does_not_mutate_input(self):
        blocks = [_block("b0", [10])]
        original = copy.deepcopy(blocks)
        blocks_containing_line(blocks, 10)
        assert blocks == original


class TestForwardReachable:
    def test_single_start_block_no_edges(self):
        assert forward_reachable(frozenset({"b0"}), []) == frozenset({"b0"})

    def test_follows_single_edge(self):
        edges = [_edge("b0", "b1")]
        assert forward_reachable(frozenset({"b0"}), edges) == frozenset({"b0", "b1"})

    def test_follows_chain(self):
        edges = [_edge("b0", "b1"), _edge("b1", "b2")]
        assert forward_reachable(frozenset({"b0"}), edges) == frozenset(
            {"b0", "b1", "b2"}
        )

    def test_follows_branch(self):
        edges = [_edge("b0", "b1", "T"), _edge("b0", "b2", "F")]
        result = forward_reachable(frozenset({"b0"}), edges)
        assert result == frozenset({"b0", "b1", "b2"})

    def test_does_not_follow_cycle_infinitely(self):
        edges = [_edge("b0", "b1"), _edge("b1", "b0")]
        result = forward_reachable(frozenset({"b0"}), edges)
        assert result == frozenset({"b0", "b1"})

    def test_does_not_mutate_input(self):
        edges = [_edge("b0", "b1")]
        original = copy.deepcopy(edges)
        forward_reachable(frozenset({"b0"}), edges)
        assert edges == original


class TestBackwardReachable:
    def test_single_start_block_no_edges(self):
        assert backward_reachable(frozenset({"b2"}), []) == frozenset({"b2"})

    def test_follows_edge_backwards(self):
        edges = [_edge("b0", "b1")]
        assert backward_reachable(frozenset({"b1"}), edges) == frozenset({"b0", "b1"})

    def test_follows_chain_backwards(self):
        edges = [_edge("b0", "b1"), _edge("b1", "b2")]
        assert backward_reachable(frozenset({"b2"}), edges) == frozenset(
            {"b0", "b1", "b2"}
        )

    def test_does_not_follow_cycle_infinitely(self):
        edges = [_edge("b0", "b1"), _edge("b1", "b0")]
        result = backward_reachable(frozenset({"b1"}), edges)
        assert result == frozenset({"b0", "b1"})

    def test_does_not_mutate_input(self):
        edges = [_edge("b0", "b1")]
        original = copy.deepcopy(edges)
        backward_reachable(frozenset({"b1"}), edges)
        assert edges == original


class TestSliceBlocks:
    def test_keeps_blocks_in_kept(self):
        blocks = [_block("b0", [10]), _block("b1", [20]), _block("b2", [30])]
        result = slice_blocks(blocks, frozenset({"b0", "b2"}))
        assert [b["id"] for b in result] == ["b0", "b2"]

    def test_returns_empty_when_none_kept(self):
        blocks = [_block("b0", [10])]
        assert slice_blocks(blocks, frozenset()) == []

    def test_does_not_mutate_input(self):
        blocks = [_block("b0", [10])]
        original = copy.deepcopy(blocks)
        slice_blocks(blocks, frozenset({"b0"}))
        assert blocks == original


class TestSliceEdges:
    def test_keeps_edges_with_both_endpoints_in_kept(self):
        edges = [_edge("b0", "b1"), _edge("b1", "b2"), _edge("b0", "b2")]
        result = slice_edges(edges, frozenset({"b0", "b1"}))
        assert len(result) == 1
        assert result[0]["fromBlock"] == "b0"
        assert result[0]["toBlock"] == "b1"

    def test_drops_edges_with_missing_source(self):
        edges = [_edge("b99", "b1")]
        assert slice_edges(edges, frozenset({"b1"})) == []

    def test_drops_edges_with_missing_target(self):
        edges = [_edge("b0", "b99")]
        assert slice_edges(edges, frozenset({"b0"})) == []

    def test_does_not_mutate_input(self):
        edges = [_edge("b0", "b1")]
        original = copy.deepcopy(edges)
        slice_edges(edges, frozenset({"b0", "b1"}))
        assert edges == original


class TestSliceTraps:
    def _trap(
        self, handler: str, covered: list[str], handler_blocks: list[str]
    ) -> dict:
        return {
            "handler": handler,
            "type": "java.lang.Exception",
            "coveredBlocks": covered,
            "handlerBlocks": handler_blocks,
        }

    def test_keeps_trap_when_covered_blocks_intersect_kept(self):
        trap = self._trap("h0", ["b0", "b1"], ["h0"])
        result = slice_traps([trap], frozenset({"b0"}))
        assert len(result) == 1

    def test_keeps_trap_when_handler_blocks_intersect_kept(self):
        trap = self._trap("h0", ["b5"], ["h0", "h1"])
        result = slice_traps([trap], frozenset({"h0"}))
        assert len(result) == 1

    def test_drops_trap_with_no_intersection(self):
        trap = self._trap("h0", ["b5", "b6"], ["h0"])
        result = slice_traps([trap], frozenset({"b0", "b1"}))
        assert result == []

    def test_trims_covered_blocks_to_intersection(self):
        trap = self._trap("h0", ["b0", "b1", "b2"], ["h0"])
        result = slice_traps([trap], frozenset({"b0", "b2"}))
        assert frozenset(result[0]["coveredBlocks"]) == frozenset({"b0", "b2"})

    def test_trims_handler_blocks_to_intersection(self):
        trap = self._trap("h0", ["b0"], ["h0", "h1", "h2"])
        result = slice_traps([trap], frozenset({"b0", "h0", "h2"}))
        assert frozenset(result[0]["handlerBlocks"]) == frozenset({"h0", "h2"})

    def test_does_not_mutate_input(self):
        trap = self._trap("h0", ["b0"], ["h0"])
        original = copy.deepcopy([trap])
        slice_traps([trap], frozenset({"b0"}))
        assert [trap] == original


class TestLinesInKeptBlocks:
    def test_collects_lines_from_kept_blocks(self):
        blocks = [_block("b0", [10, 11]), _block("b1", [20]), _block("b2", [30])]
        result = lines_in_kept_blocks(blocks, frozenset({"b0", "b2"}))
        assert result == frozenset({10, 11, 30})

    def test_excludes_lines_from_dropped_blocks(self):
        blocks = [_block("b0", [10]), _block("b1", [20])]
        result = lines_in_kept_blocks(blocks, frozenset({"b0"}))
        assert 20 not in result

    def test_returns_empty_when_no_kept_blocks(self):
        blocks = [_block("b0", [10])]
        assert lines_in_kept_blocks(blocks, frozenset()) == frozenset()

    def test_does_not_mutate_input(self):
        blocks = [_block("b0", [10])]
        original = copy.deepcopy(blocks)
        lines_in_kept_blocks(blocks, frozenset({"b0"}))
        assert blocks == original


class TestSliceSourceTrace:
    def test_keeps_entries_in_kept_lines(self):
        trace = [{"line": 10, "calls": []}, {"line": 20}, {"line": 30}]
        result = slice_source_trace(trace, frozenset({10, 30}))
        assert [e["line"] for e in result] == [10, 30]

    def test_returns_empty_when_no_match(self):
        trace = [{"line": 10}]
        assert slice_source_trace(trace, frozenset({99})) == []

    def test_does_not_mutate_input(self):
        trace = [{"line": 10}]
        original = copy.deepcopy(trace)
        slice_source_trace(trace, frozenset({10}))
        assert trace == original


class TestSliceChildren:
    def _child(self, call_site_line: int, sig: str = "") -> dict:
        return {
            "class": "com.example.Svc",
            "method": "m",
            "methodSignature": sig or f"<Svc: void m{call_site_line}()>",
            "ref": True,
            "callSiteLine": call_site_line,
        }

    def test_keeps_children_whose_callsite_line_is_in_kept_lines(self):
        children = [self._child(10), self._child(20), self._child(30)]
        result = slice_children(children, frozenset({10, 30}))
        assert [c["callSiteLine"] for c in result] == [10, 30]

    def test_drops_children_outside_kept_lines(self):
        children = [self._child(99)]
        assert slice_children(children, frozenset({10})) == []

    def test_does_not_mutate_input(self):
        children = [self._child(10)]
        original = copy.deepcopy(children)
        slice_children(children, frozenset({10}))
        assert children == original


class TestIntraSlice:
    """Integration tests for the intra_slice composer."""

    def _cfg(
        self,
        blocks: list[dict],
        edges: list[dict],
        source_trace: list[dict] | None = None,
        children: list[dict] | None = None,
    ) -> dict:
        return {
            "class": "com.example.Svc",
            "method": "process",
            "methodSignature": "<Svc: void process()>",
            "blocks": blocks,
            "edges": edges,
            "traps": [],
            "sourceTrace": source_trace or [],
            "children": children or [],
        }

    def test_linear_path_kept_in_full(self):
        # b0(10) → b1(20) → b2(30); slice 10..30 keeps all
        blocks = [_block("b0", [10]), _block("b1", [20]), _block("b2", [30])]
        edges = [_edge("b0", "b1"), _edge("b1", "b2")]
        cfg = self._cfg(blocks, edges)
        result = intra_slice(cfg, 10, 30)
        assert frozenset(b["id"] for b in result["blocks"]) == frozenset(
            {"b0", "b1", "b2"}
        )

    def test_dead_branch_pruned(self):
        # b0(10) → b1(20) [T]
        #        → b2(30) [F] → b3(40)
        # slice 10..20: only b0 and b1 survive
        blocks = [
            _block("b0", [10]),
            _block("b1", [20]),
            _block("b2", [30]),
            _block("b3", [40]),
        ]
        edges = [
            _edge("b0", "b1", "T"),
            _edge("b0", "b2", "F"),
            _edge("b2", "b3"),
        ]
        cfg = self._cfg(blocks, edges)
        result = intra_slice(cfg, 10, 20)
        kept_ids = frozenset(b["id"] for b in result["blocks"])
        assert kept_ids == frozenset({"b0", "b1"})
        assert "b2" not in kept_ids
        assert "b3" not in kept_ids

    def test_source_trace_filtered_to_kept_lines(self):
        blocks = [_block("b0", [10]), _block("b1", [20])]
        edges = [_edge("b0", "b1")]
        source_trace = [{"line": 10}, {"line": 20}, {"line": 99}]
        cfg = self._cfg(blocks, edges, source_trace=source_trace)
        result = intra_slice(cfg, 10, 20)
        assert [e["line"] for e in result["sourceTrace"]] == [10, 20]

    def test_children_filtered_by_callsite_line(self):
        blocks = [_block("b0", [10]), _block("b1", [20])]
        edges = [_edge("b0", "b1")]
        children = [
            {
                "class": "com.example.Svc",
                "method": "a",
                "methodSignature": "<Svc: void a()>",
                "ref": True,
                "callSiteLine": 10,
            },
            {
                "class": "com.example.Svc",
                "method": "b",
                "methodSignature": "<Svc: void b()>",
                "ref": True,
                "callSiteLine": 99,
            },
        ]
        cfg = self._cfg(blocks, edges, children=children)
        result = intra_slice(cfg, 10, 20)
        assert len(result["children"]) == 1
        assert result["children"][0]["callSiteLine"] == 10

    def test_does_not_mutate_input(self):
        blocks = [_block("b0", [10]), _block("b1", [20])]
        edges = [_edge("b0", "b1")]
        cfg = self._cfg(blocks, edges)
        original = copy.deepcopy(cfg)
        intra_slice(cfg, 10, 20)
        assert cfg == original
