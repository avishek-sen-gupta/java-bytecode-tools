"""Tests for ftrace_to_dot trap cluster assignment.

Verifies that handler blocks are never placed inside try (covered) clusters,
even when a block is both a coveredBlock for one trap and a handlerBlock for another.
"""

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


def _quoted_value(line: str, key: str) -> str | None:
    """Extract the value for key="value" from a DOT line."""
    tag = f'{key}="'
    start = line.find(tag)
    if start == -1:
        return None
    start += len(tag)
    end = line.index('"', start)
    return line[start:end]


def _parse_subgraphs(dot: str) -> dict[str, set[str]]:
    """Parse DOT text into {subgraph_label: set of node IDs}."""
    result: dict[str, set[str]] = {}
    label = None
    nodes: set[str] = set()
    depth = 0

    for line in dot.splitlines():
        stripped = line.strip()
        if stripped.startswith("subgraph "):
            depth = 1
            label = None
            nodes = set()
        elif depth > 0:
            if "label=" in stripped:
                label = _quoted_value(stripped, "label")
            # Node lines look like "n3;" — starts with n, has digits, ends with ;
            if stripped.startswith("n") and stripped.endswith(";"):
                token = stripped[:-1].strip()
                if token[1:].isdigit():
                    nodes.add(token)
            if "}" in stripped:
                depth -= 1
                if depth == 0 and label is not None:
                    result[label] = nodes
    return result


def _blocks_in_subgraph(dot: str, subgraph_label: str) -> set[str]:
    """Return node IDs declared inside a subgraph with the given label."""
    return _parse_subgraphs(dot).get(subgraph_label, set())


def _node_id_for_label(dot: str, label_fragment: str) -> str | None:
    """Find the node ID whose label contains the given fragment."""
    for line in dot.splitlines():
        if label_fragment in line and "[label=" in line:
            token = line.strip().split()[0]
            if token.startswith("n") and token[1:].isdigit():
                return token
    return None


def _exception_edges(dot: str) -> list[dict]:
    """Extract exception edges (dashed, orange) with their ltail/lhead attributes."""
    results = []
    for line in dot.splitlines():
        if 'style="dashed"' not in line or "#ffa500" not in line or "->" not in line:
            continue
        stripped = line.strip()
        arrow = stripped.index("->")
        src = stripped[:arrow].strip()
        rest = stripped[arrow + 2 :].strip()
        dst = rest.split()[0]
        results.append(
            {
                "src": src,
                "dst": dst,
                "ltail": _quoted_value(line, "ltail"),
                "lhead": _quoted_value(line, "lhead"),
                "label": _quoted_value(line, "label"),
            }
        )
    return results


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


class TestDuplicateBlockMerging:
    """Blocks with identical content in the same cluster should be merged."""

    def _build_finally_duplicate_fixture(self):
        """
        Simulates the Java compiler's inlined finally pattern:
        - B12: exception-path finally (L14, L15), no successors (re-throws)
        - B13: normal-path finally (L14, L15), successor B14 (return)
        Both are in Throwable's handlerBlocks → same cluster → should merge.
        """
        blocks = [
            {"id": "B0", "stmts": [{"line": 6}], "successors": ["B1"]},
            {
                "id": "B1",
                "stmts": [{"line": 7, "call": "println"}],
                "successors": ["B13"],
            },
            {
                "id": "B12",
                "stmts": [{"line": 14, "call": "println"}, {"line": 15}],
                "successors": [],
            },
            {
                "id": "B13",
                "stmts": [{"line": 14, "call": "println"}, {"line": 15}],
                "successors": ["B14"],
            },
            {"id": "B14", "stmts": [{"line": 16}], "successors": []},
        ]
        traps = [
            {
                "type": "java.lang.Throwable",
                "handler": "B12",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B12", "B13"],
            },
        ]
        return blocks, traps

    def test_merged_blocks_produce_single_set_of_nodes(self):
        """B12 and B13 have identical content — only one L14 and one L15 in finally."""
        blocks, traps = self._build_finally_duplicate_fixture()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        finally_nodes = _blocks_in_subgraph(dot, "finally")
        # Count L14 and L15 nodes within the finally cluster
        l14_count = 0
        l15_count = 0
        for line in dot.splitlines():
            stripped = line.strip()
            for nid in finally_nodes:
                if stripped.startswith(f"{nid} ") and "[label=" in stripped:
                    if "L14" in stripped:
                        l14_count += 1
                    if "L15" in stripped:
                        l15_count += 1
        assert l14_count == 1, f"Expected 1 L14 node in finally, got {l14_count}"
        assert l15_count == 1, f"Expected 1 L15 node in finally, got {l15_count}"

    def test_merged_block_preserves_successor_edges(self):
        """After merging B13 into B12, the edge B13→B14 should still render (via B12's nodes)."""
        blocks, traps = self._build_finally_duplicate_fixture()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        # Find the L15 node (last in finally) and L16 node
        n_l15 = _node_id_for_label(dot, "L15")
        n_l16 = _node_id_for_label(dot, "L16")
        assert n_l15 is not None, "L15 node should exist"
        assert n_l16 is not None, "L16 node should exist"

        # There should be an edge from L15 to L16 (B13's successor B14)
        edge_found = any(f"{n_l15} -> {n_l16}" in line for line in dot.splitlines())
        assert edge_found, f"Edge from {n_l15} (L15) to {n_l16} (L16) should exist"

    def test_merged_block_preserves_incoming_edges(self):
        """After merging, B1→B13 should render as B1→B12's first node."""
        blocks, traps = self._build_finally_duplicate_fixture()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        # L7 (B1) should connect to L14 (merged finally entry)
        n_l7 = _node_id_for_label(dot, "L7")
        n_l14 = _node_id_for_label(dot, "L14")
        assert n_l7 is not None
        assert n_l14 is not None

        edge_found = any(f"{n_l7} -> {n_l14}" in line for line in dot.splitlines())
        assert edge_found, f"Edge from {n_l7} (L7) to {n_l14} (L14) should exist"

    def test_no_merge_across_clusters(self):
        """Blocks with identical content in different clusters should NOT merge."""
        blocks = [
            {"id": "B0", "stmts": [{"line": 5}], "successors": ["B1"]},
            {
                "id": "B1",
                "stmts": [{"line": 14, "call": "println"}, {"line": 15}],
                "successors": [],
            },
            {
                "id": "B2",
                "stmts": [{"line": 14, "call": "println"}, {"line": 15}],
                "successors": [],
            },
        ]
        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B1",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B1"],
            },
            {
                "type": "java.lang.Throwable",
                "handler": "B2",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B2"],
            },
        ]
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        # Both clusters should have their own L14 node
        catch_nodes = _blocks_in_subgraph(dot, "catch (RuntimeException)")
        finally_nodes = _blocks_in_subgraph(dot, "finally")
        assert len(catch_nodes) > 0, "catch cluster should have nodes"
        assert len(finally_nodes) > 0, "finally cluster should have nodes"
        assert catch_nodes.isdisjoint(finally_nodes), "clusters should not share nodes"

    def test_no_merge_when_content_differs(self):
        """Blocks with different content in the same cluster should not merge."""
        blocks = [
            {"id": "B0", "stmts": [{"line": 5}], "successors": []},
            {
                "id": "B1",
                "stmts": [{"line": 14, "call": "println"}],
                "successors": ["B2"],
            },
            {"id": "B2", "stmts": [{"line": 15, "call": "cleanup"}], "successors": []},
        ]
        traps = [
            {
                "type": "java.lang.Throwable",
                "handler": "B1",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B1", "B2"],
            },
        ]
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        finally_nodes = _blocks_in_subgraph(dot, "finally")
        assert (
            len(finally_nodes) == 2
        ), f"Expected 2 nodes (L14 + L15), got {len(finally_nodes)}"


class TestExceptionEdgeRendering:
    """Exception edges must source from blocks in the correct cluster."""

    def _build_overlapping_trap_fixture(self):
        """Two traps where all covered blocks are assigned to trap 0's try cluster."""
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
            {
                "id": "B4",
                "stmts": [{"line": 18, "call": "done"}],
                "successors": ["B5"],
            },
            {
                "id": "B5",
                "stmts": [{"line": 19, "call": "cleanup"}],
                "successors": [],
            },
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

    def test_exception_edge_source_in_try_cluster(self):
        """Exception edge source must be a node in the trap's own try cluster."""
        blocks, traps = self._build_overlapping_trap_fixture()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)
        edges = _exception_edges(dot)

        re_edge = next((e for e in edges if e["label"] == "RuntimeException"), None)
        assert re_edge is not None, "RuntimeException exception edge should exist"

        # Source node must be in try(RuntimeException) cluster
        try_re_nodes = _blocks_in_subgraph(dot, "try (RuntimeException)")
        assert (
            re_edge["src"] in try_re_nodes
        ), f"edge source {re_edge['src']} should be in try(RuntimeException)"

    def test_exception_edge_exists_for_empty_try_cluster(self):
        """When a trap's try cluster has no blocks, exception edge should still be drawn."""
        blocks, traps = self._build_overlapping_trap_fixture()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)
        edges = _exception_edges(dot)

        throwable_edge = next((e for e in edges if e["label"] == "Throwable"), None)
        assert (
            throwable_edge is not None
        ), "Throwable exception edge should exist even when try cluster is empty"
        # ltail must not reference the empty cluster
        assert (
            throwable_edge["ltail"] is None
            or throwable_edge["ltail"] != "cluster_0_try_1"
        ), "ltail should not reference empty try cluster"

    def test_ltail_lhead_reference_nonempty_clusters(self):
        """When ltail/lhead are present, the referenced clusters must have nodes."""
        blocks, traps = self._build_overlapping_trap_fixture()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        # Build a map of cluster_id → set of node IDs from the DOT
        cluster_nodes: dict[str, set[str]] = {}
        current_cluster = None
        nodes: set[str] = set()
        for line in dot.splitlines():
            stripped = line.strip()
            if stripped.startswith("subgraph "):
                current_cluster = stripped.split()[1]
                nodes = set()
            elif current_cluster:
                if stripped.startswith("n") and stripped.endswith(";"):
                    token = stripped[:-1].strip()
                    if token[1:].isdigit():
                        nodes.add(token)
                if "}" in stripped:
                    cluster_nodes[current_cluster] = nodes
                    current_cluster = None

        for edge in _exception_edges(dot):
            if edge["ltail"]:
                cluster_name = edge["ltail"]
                assert (
                    cluster_name in cluster_nodes
                ), f"ltail cluster {cluster_name} should exist in DOT"
                assert (
                    len(cluster_nodes[cluster_name]) > 0
                ), f"ltail cluster {cluster_name} should have nodes"


def _cfg_edges(dot: str) -> list[tuple[str, str, str]]:
    """Extract CFG edges as (src, dst, label) tuples.

    Only includes normal CFG edges (not exception/dashed edges).
    """
    edges = []
    for line in dot.splitlines():
        stripped = line.strip()
        if "->" not in stripped or "dashed" in stripped:
            continue
        arrow = stripped.index("->")
        src = stripped[:arrow].strip()
        rest = stripped[arrow + 2 :].strip()
        dst = rest.split()[0].rstrip(";")
        label = _quoted_value(stripped, "label") or ""
        edges.append((src, dst, label))
    return edges


class TestMergedBlockEdgeDedup:
    """When multiple blocks merge to the same DOT node, suppress self-loops and duplicates."""

    def _build_chain_same_line(self):
        """
        Simulates `throw new RuntimeException(msg)` — 5 blocks on L9:
        B2→B3→B4→B5→B6 (new, dup, ldc, invokespecial, athrow).
        B5 has a call, the rest don't, so merge_block_stmts produces
        two groups: {B2,B3,B4,B6}→plain L9 node, {B5}→L9+call node.
        Without dedup: self-loops on plain L9 and a back-edge from call→plain.
        """
        blocks = [
            {"id": "B0", "stmts": [{"line": 6}], "successors": ["B1"]},
            {
                "id": "B1",
                "stmts": [{"line": 6}],
                "branchCondition": "i <= 0",
                "successors": ["B7", "B2"],
            },
            {"id": "B2", "stmts": [{"line": 9}], "successors": ["B3"]},
            {"id": "B3", "stmts": [{"line": 9}], "successors": ["B4"]},
            {"id": "B4", "stmts": [{"line": 9}], "successors": ["B5"]},
            {
                "id": "B5",
                "stmts": [{"line": 9, "call": "RuntimeException.<init>"}],
                "successors": ["B6"],
            },
            {"id": "B6", "stmts": [{"line": 9}], "successors": []},
            {"id": "B7", "stmts": [{"line": 7}], "successors": []},
        ]
        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B7",
                "coveredBlocks": ["B0", "B1", "B2", "B3", "B4", "B5", "B6"],
                "handlerBlocks": ["B7"],
            },
        ]
        return blocks, traps

    def test_no_self_loops(self):
        """Merged blocks must not produce self-loop edges."""
        blocks, traps = self._build_chain_same_line()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)
        edges = _cfg_edges(dot)

        self_loops = [(s, d, l) for s, d, l in edges if s == d]
        assert self_loops == [], f"Self-loops found: {self_loops}"

    def test_no_duplicate_edges(self):
        """Each (src, dst, label) triple should appear at most once."""
        blocks, traps = self._build_chain_same_line()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)
        edges = _cfg_edges(dot)

        seen = set()
        dupes = []
        for e in edges:
            if e in seen:
                dupes.append(e)
            seen.add(e)
        assert dupes == [], f"Duplicate edges found: {dupes}"

    def test_forward_edge_preserved(self):
        """The edge from plain L9 to L9+call should exist."""
        blocks, traps = self._build_chain_same_line()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        n_l9_plain = _node_id_for_label(dot, "L9")
        n_l9_call = _node_id_for_label(dot, "RuntimeException.<init>")
        assert n_l9_plain is not None
        assert n_l9_call is not None

        edges = _cfg_edges(dot)
        assert (
            n_l9_plain,
            n_l9_call,
            "",
        ) in edges, f"Expected edge {n_l9_plain} -> {n_l9_call}"

    def test_no_reverse_edge_from_merged_blocks(self):
        """Back-edge from L9+call to plain L9 is a merge artifact and must not appear."""
        blocks, traps = self._build_chain_same_line()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)

        n_l9_plain = _node_id_for_label(dot, "L9")
        n_l9_call = _node_id_for_label(dot, "RuntimeException.<init>")

        edges = _cfg_edges(dot)
        assert (
            n_l9_call,
            n_l9_plain,
            "",
        ) not in edges, f"Reverse edge {n_l9_call} -> {n_l9_plain} should not exist"

    def test_branch_edges_not_suppressed(self):
        """T/F branch edges should still render even after dedup logic."""
        blocks, traps = self._build_chain_same_line()
        root = _make_method_with_traps(blocks, traps)
        dot = build_dot(root)
        edges = _cfg_edges(dot)

        t_edges = [(s, d) for s, d, l in edges if l == "T"]
        f_edges = [(s, d) for s, d, l in edges if l == "F"]
        assert len(t_edges) == 1, f"Expected 1 T edge, got {t_edges}"
        assert len(f_edges) == 1, f"Expected 1 F edge, got {f_edges}"
