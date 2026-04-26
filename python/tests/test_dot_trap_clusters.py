"""Tests for ftrace_to_dot trap cluster assignment.

Verifies that handler blocks are never placed inside try (covered) clusters,
even when a block is both a coveredBlock for one trap and a handlerBlock for another.
"""

import re

from ftrace_to_dot import assign_trap_clusters, blocks_for_cluster, build_dot


def _make_method_with_traps(blocks, traps):
    """Build a minimal method node with given blocks and traps."""
    return {
        "class": "com.example.Svc",
        "method": "handle",
        "lineStart": 1,
        "lineEnd": 20,
        "blocks": blocks,
        "traps": traps,
        "children": [],
    }


def _blocks_in_subgraph(dot: str, subgraph_label: str) -> set[str]:
    """Extract node IDs declared inside a subgraph with the given label."""
    # Find the subgraph block by label, then collect node IDs within it
    pattern = (
        rf'subgraph\s+\w+\s*\{{[^{{}}]*?label="{re.escape(subgraph_label)}"[^{{}}]*?\}}'
    )
    match = re.search(pattern, dot, re.DOTALL)
    if not match:
        return set()
    block = match.group(0)
    # Node IDs are lines like "    n3;"
    return set(re.findall(r"\b(n\d+)\s*;", block))


def _node_id_for_label(dot: str, label_fragment: str) -> str | None:
    """Find the node ID whose label contains the given fragment."""
    pattern = rf'(n\d+)\s+\[label="[^"]*{re.escape(label_fragment)}[^"]*"'
    match = re.search(pattern, dot)
    return match.group(1) if match else None


class TestTrapClusterAssignment:
    """Handler blocks must not appear in try (covered) clusters."""

    def _build_overlapping_trap_fixture(self):
        """
        Two traps where catch handler blocks are also covered by the finally trap:
        - Trap 0: RuntimeException, covered=[B0,B1], handler=B2, handlerBlocks=[B2,B3]
        - Trap 1: Throwable(finally), covered=[B0,B1,B2,B3], handler=B4, handlerBlocks=[B4,B5]

        B2,B3 are handler blocks for trap 0 but also covered by trap 1.
        They should appear in the catch cluster, NOT in the try(Throwable) cluster.
        """
        blocks = [
            {"id": "B0", "stmts": [{"line": 5, "call": "foo"}], "successors": ["B1"]},
            {"id": "B1", "stmts": [{"line": 6, "call": "bar"}], "successors": ["B2"]},
            {
                "id": "B2",
                "stmts": [{"line": 11, "call": "errLog"}],
                "successors": ["B3"],
            },
            {
                "id": "B3",
                "stmts": [{"line": 12, "call": "errMsg"}],
                "successors": ["B4"],
            },
            {"id": "B4", "stmts": [{"line": 18, "call": "done"}], "successors": ["B5"]},
            {"id": "B5", "stmts": [{"line": 19, "call": "cleanup"}], "successors": []},
        ]
        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B2",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B2", "B3"],
            },
            {
                "type": "java.lang.Throwable",
                "handler": "B4",
                "coveredBlocks": ["B0", "B1", "B2", "B3"],
                "handlerBlocks": ["B4", "B5"],
            },
        ]
        return blocks, traps

    def test_handler_blocks_not_in_try_cluster(self):
        """B2/B3 (catch handler) must not appear in try(Throwable) cluster."""
        blocks, traps = self._build_overlapping_trap_fixture()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        # Find nodes for L11, L12 (the catch handler lines)
        n_l11 = _node_id_for_label(dot, "L11")
        n_l12 = _node_id_for_label(dot, "L12")
        assert n_l11 is not None, "L11 node should exist"
        assert n_l12 is not None, "L12 node should exist"

        # These nodes should NOT be in try(Throwable)
        try_throwable_nodes = _blocks_in_subgraph(dot, "try (Throwable)")
        assert (
            n_l11 not in try_throwable_nodes
        ), f"L11 ({n_l11}) should not be in try(Throwable) cluster"
        assert (
            n_l12 not in try_throwable_nodes
        ), f"L12 ({n_l12}) should not be in try(Throwable) cluster"

    def test_handler_blocks_in_correct_handler_cluster(self):
        """B2/B3 should appear in catch(RuntimeException), B4/B5 in finally."""
        blocks, traps = self._build_overlapping_trap_fixture()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        n_l11 = _node_id_for_label(dot, "L11")
        n_l12 = _node_id_for_label(dot, "L12")
        n_l18 = _node_id_for_label(dot, "L18")
        n_l19 = _node_id_for_label(dot, "L19")

        catch_nodes = _blocks_in_subgraph(dot, "catch (RuntimeException)")
        finally_nodes = _blocks_in_subgraph(dot, "finally")

        assert n_l11 in catch_nodes, f"L11 should be in catch(RuntimeException)"
        assert n_l12 in catch_nodes, f"L12 should be in catch(RuntimeException)"
        assert n_l18 in finally_nodes, f"L18 should be in finally"
        assert n_l19 in finally_nodes, f"L19 should be in finally"

    def test_try_cluster_only_has_non_handler_blocks(self):
        """Try clusters should only contain blocks that aren't handlers for any trap."""
        blocks, traps = self._build_overlapping_trap_fixture()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        n_l5 = _node_id_for_label(dot, "L5")
        n_l6 = _node_id_for_label(dot, "L6")

        # B0/B1 (L5/L6) should be in try(RuntimeException) — they're covered, not handlers
        try_re_nodes = _blocks_in_subgraph(dot, "try (RuntimeException)")
        assert n_l5 in try_re_nodes, "L5 should be in try(RuntimeException)"
        assert n_l6 in try_re_nodes, "L6 should be in try(RuntimeException)"

    def test_no_handler_overlap_single_trap(self):
        """With a single trap, handler blocks should not appear in the try cluster."""
        blocks = [
            {"id": "B0", "stmts": [{"line": 5, "call": "foo"}], "successors": ["B1"]},
            {"id": "B1", "stmts": [{"line": 10, "call": "handle"}], "successors": []},
        ]
        traps = [
            {
                "type": "java.lang.Exception",
                "handler": "B1",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B1"],
            },
        ]
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        n_l10 = _node_id_for_label(dot, "L10")
        try_nodes = _blocks_in_subgraph(dot, "try (Exception)")
        assert n_l10 not in try_nodes, "handler block should not be in try cluster"


class TestAssignTrapClusters:
    """Unit tests for the pure assign_trap_clusters function."""

    def test_handler_wins_over_coverage(self):
        """A block that is both covered and a handler gets assigned to handler."""
        traps = [
            {"type": "RE", "coveredBlocks": ["B0", "B1"], "handlerBlocks": ["B2"]},
            {
                "type": "Throwable",
                "coveredBlocks": ["B0", "B1", "B2"],
                "handlerBlocks": ["B3"],
            },
        ]
        result = assign_trap_clusters(traps)
        assert result["B2"] == ("handler", 0)
        assert result["B3"] == ("handler", 1)

    def test_covered_blocks_assigned_to_first_trap(self):
        """A block covered by multiple traps is assigned to the first one seen."""
        traps = [
            {"type": "RE", "coveredBlocks": ["B0"], "handlerBlocks": ["B1"]},
            {"type": "Throwable", "coveredBlocks": ["B0"], "handlerBlocks": ["B2"]},
        ]
        result = assign_trap_clusters(traps)
        assert result["B0"] == ("try", 0)

    def test_no_overwrites(self):
        """Once assigned, a block is never reassigned."""
        traps = [
            {"type": "RE", "coveredBlocks": ["B0"], "handlerBlocks": ["B1"]},
            {
                "type": "Throwable",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B2"],
            },
        ]
        result = assign_trap_clusters(traps)
        # B0 assigned as try/0 first, not overwritten by try/1
        assert result["B0"] == ("try", 0)
        # B1 is handler/0, not overwritten by coverage in trap 1
        assert result["B1"] == ("handler", 0)

    def test_empty_traps(self):
        assert assign_trap_clusters([]) == {}

    def test_blocks_for_cluster_filters_correctly(self):
        traps = [
            {"type": "RE", "coveredBlocks": ["B0"], "handlerBlocks": ["B1"]},
            {
                "type": "Throwable",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B2"],
            },
        ]
        assignment = assign_trap_clusters(traps)
        assert blocks_for_cluster(assignment, "try", 0) == ["B0"]
        assert blocks_for_cluster(assignment, "handler", 0) == ["B1"]
        assert blocks_for_cluster(assignment, "handler", 1) == ["B2"]
        assert blocks_for_cluster(assignment, "try", 1) == []
