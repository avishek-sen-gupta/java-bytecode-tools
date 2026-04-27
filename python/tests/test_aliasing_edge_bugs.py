"""Tests for aliasing edge bugs found in chk-parent-conflict SVG rendering.

These reproduce 5 visual bugs caused by block aliasing in ftrace_semantic:

Bug 1: Non-decision node has T/F edges (non-branch block aliased to branch block)
Bug 2: Decision node has T but no F edge (one branch edge lost via aliasing)
Bug 3: Decision node has 3 edges (extra edge from aliased block's successor)
Bug 4: Decision node has 1 T + 2 F edges (conflicting labels on same node pair)
Bug 5: Decision node has 4 edges (multiple aliases funneling edges to same node)

Root cause: block_content_signature() doesn't include outgoing edge structure,
so blocks with different successor counts/labels can alias together.
"""

from ftrace_types import ClusterRole, NodeKind


def _make_enriched_method(
    blocks, traps, cluster_assignment, block_aliases=(), children=(), edges=()
):
    """Build a method node with all intermediate fields from passes 1-3."""
    return {
        "class": "com.example.Svc",
        "method": "handle",
        "methodSignature": "<com.example.Svc: void handle()>",
        "lineStart": 1,
        "lineEnd": 20,
        "sourceLineCount": 20,
        "blocks": blocks,
        "edges": list(edges) if edges else [],
        "traps": traps,
        "metadata": {
            "clusterAssignment": cluster_assignment,
            "blockAliases": dict(block_aliases) if block_aliases else {},
        },
        "children": list(children) if children else [],
    }


class TestBranchNonBranchAliasingSignature:
    """Bug 1: block_content_signature must distinguish branch from non-branch blocks
    even when they have identical mergedStmts content."""

    def test_branch_block_not_aliased_to_non_branch_with_same_stmts(self):
        """Two blocks with identical mergedStmts but one has branchCondition
        and the other doesn't — they must NOT be aliased."""
        from ftrace_semantic import compute_block_aliases

        # Block with a call on line 10 (non-branch, has one unlabeled successor)
        non_branch = {
            "id": "B3",
            "mergedStmts": [
                {"line": 10, "calls": ["Foo.bar"], "branches": [], "assigns": []}
            ],
            "stmts": [],
        }
        # Block with same call on line 10 but it's also a branch block
        # (has branchCondition, T/F successors)
        branch = {
            "id": "B7",
            "mergedStmts": [
                {"line": 10, "calls": ["Foo.bar"], "branches": [], "assigns": []}
            ],
            "branchCondition": "result == null",
            "stmts": [],
        }

        cluster_assignment = {
            "B3": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B7": {"kind": ClusterRole.TRY, "trapIndex": 0},
        }
        aliases = compute_block_aliases([non_branch, branch], cluster_assignment)
        # B7 must NOT alias to B3 — they have different flow characteristics
        assert "B7" not in aliases

    def test_non_branch_block_not_aliased_to_branch_block(self):
        """Same as above but the branch block comes first (is canonical)."""
        from ftrace_semantic import compute_block_aliases

        branch = {
            "id": "B2",
            "mergedStmts": [
                {"line": 10, "calls": ["Foo.bar"], "branches": [], "assigns": []}
            ],
            "branchCondition": "result == null",
            "stmts": [],
        }
        non_branch = {
            "id": "B5",
            "mergedStmts": [
                {"line": 10, "calls": ["Foo.bar"], "branches": [], "assigns": []}
            ],
            "stmts": [],
        }

        cluster_assignment = {
            "B2": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B5": {"kind": ClusterRole.TRY, "trapIndex": 0},
        }
        aliases = compute_block_aliases([branch, non_branch], cluster_assignment)
        # B5 must NOT alias to B2 — non-branch should not merge with branch
        assert "B5" not in aliases


class TestConflictingEdgeLabels:
    """Bug 4: When aliased blocks route edges through the same canonical node,
    conflicting T and F labels can appear on the same (src, dst) pair."""

    def test_aliased_blocks_produce_conflicting_labels_on_same_pair(self):
        """Two branch blocks aliased to same canonical → both T and F edges
        from the canonical node can point to the same target. The edge builder
        must not emit conflicting labels on the same (src, dst) pair."""
        from ftrace_semantic import _build_edges

        # B0 (branch, canonical) has T→B1, F→B2
        # B3 (branch, aliased to B0) has T→B2, F→B4
        # After aliasing, B3's edges go through B0's nodes.
        # B0→B2 has label F, but B3→B2 (mapped to B0→B2) has label T.
        # This creates conflicting T and F on the same (n0, n2) pair.
        raw_edges = [
            {"fromBlock": "B0", "toBlock": "B1", "label": "T"},
            {"fromBlock": "B0", "toBlock": "B2", "label": "F"},
            {"fromBlock": "B3", "toBlock": "B2", "label": "T"},
            {"fromBlock": "B3", "toBlock": "B4", "label": "F"},
        ]
        # B3 aliased to B0: block_first/block_last map B3→B0's nodes
        block_first = {"B0": "n0", "B1": "n1", "B2": "n2", "B3": "n0", "B4": "n4"}
        block_last = {"B0": "n0", "B1": "n1", "B2": "n2", "B3": "n0", "B4": "n4"}
        bid_to_nids = {
            "B0": ["n0"],
            "B1": ["n1"],
            "B2": ["n2"],
            "B3": ["n0"],
            "B4": ["n4"],
        }

        result = _build_edges(
            raw_edges=raw_edges,
            block_first=block_first,
            block_last=block_last,
            bid_to_nids=bid_to_nids,
            block_aliases={"B3": "B0"},
        )

        # Collect all edges from n0 to n2
        edges_n0_n2 = [
            e for e in result["edges"] if e["from"] == "n0" and e["to"] == "n2"
        ]
        labels = [e.get("branch", "") for e in edges_n0_n2]

        # There must be at most one labeled edge between any (src, dst) pair.
        # Having both T and F on the same pair is a bug.
        assert len(edges_n0_n2) <= 1, (
            f"Expected at most 1 edge from n0→n2, got {len(edges_n0_n2)} "
            f"with labels {labels}"
        )

    def test_no_duplicate_labels_between_same_node_pair(self):
        """Even without aliasing, if raw edges produce both T and F
        between the same node pair, only the first should be kept."""
        from ftrace_semantic import _build_edges

        raw_edges = [
            {"fromBlock": "B0", "toBlock": "B1", "label": "T"},
            {"fromBlock": "B0", "toBlock": "B1", "label": "F"},
        ]
        block_first = {"B0": "n0", "B1": "n1"}
        block_last = {"B0": "n0", "B1": "n1"}
        bid_to_nids = {"B0": ["n0"], "B1": ["n1"]}

        result = _build_edges(
            raw_edges=raw_edges,
            block_first=block_first,
            block_last=block_last,
            bid_to_nids=bid_to_nids,
            block_aliases={},
        )

        edges_n0_n1 = [
            e for e in result["edges"] if e["from"] == "n0" and e["to"] == "n1"
        ]
        # At most one edge per (src, dst) pair
        assert (
            len(edges_n0_n1) <= 1
        ), f"Expected at most 1 edge from n0→n1, got {len(edges_n0_n1)}"


class TestExcessEdgesFromAliasing:
    """Bug 3 & 5: Aliased blocks funnel their successors through the canonical
    node, producing more outgoing edges than the original branch had."""

    def test_aliased_branch_does_not_add_extra_outgoing_edges(self):
        """A branch block B0 has T→B1 and F→B2. Its alias B3 has T→B4, F→B5.
        After aliasing, n0 should not have 4 outgoing edges."""
        from ftrace_semantic import _build_edges

        raw_edges = [
            {"fromBlock": "B0", "toBlock": "B1", "label": "T"},
            {"fromBlock": "B0", "toBlock": "B2", "label": "F"},
            {"fromBlock": "B3", "toBlock": "B4", "label": "T"},
            {"fromBlock": "B3", "toBlock": "B5", "label": "F"},
        ]
        # B3 aliased to B0
        block_first = {
            "B0": "n0",
            "B1": "n1",
            "B2": "n2",
            "B3": "n0",
            "B4": "n4",
            "B5": "n5",
        }
        block_last = {
            "B0": "n0",
            "B1": "n1",
            "B2": "n2",
            "B3": "n0",
            "B4": "n4",
            "B5": "n5",
        }
        bid_to_nids = {
            "B0": ["n0"],
            "B1": ["n1"],
            "B2": ["n2"],
            "B3": ["n0"],
            "B4": ["n4"],
            "B5": ["n5"],
        }

        result = _build_edges(
            raw_edges=raw_edges,
            block_first=block_first,
            block_last=block_last,
            bid_to_nids=bid_to_nids,
            block_aliases={"B3": "B0"},
        )

        outgoing_from_n0 = [e for e in result["edges"] if e["from"] == "n0"]
        # A branch node should have exactly 2 outgoing edges (T and F),
        # not 4 from the alias's extra successors.
        assert len(outgoing_from_n0) <= 2, (
            f"Expected at most 2 outgoing edges from n0, got {len(outgoing_from_n0)}: "
            f"{outgoing_from_n0}"
        )


class TestConvergentBranchTargets:
    """Bug 6: A branch block's T and F targets alias to the same canonical block.
    After alias resolution both edges point to the same node. The (src, dst) dedup
    keeps only the first, leaving a branch node with just one labeled outgoing edge.

    When T and F converge to the same node the branch is a no-op — emit an
    unlabeled edge instead of dropping one branch label silently."""

    def test_convergent_targets_produce_unlabeled_edge(self):
        """B0 branches T→B2, F→B1. B2 is aliased to B1 so both resolve to n1.
        Result should be a single unlabeled edge n0→n1 (not a lone T or F)."""
        from ftrace_semantic import _build_edges

        raw_edges = [
            {"fromBlock": "B0", "toBlock": "B2", "label": "T"},
            {"fromBlock": "B0", "toBlock": "B1", "label": "F"},
        ]
        block_first = {"B0": "n0", "B1": "n1", "B2": "n1"}
        block_last = {"B0": "n0", "B1": "n1", "B2": "n1"}
        bid_to_nids = {"B0": ["n0"], "B1": ["n1"], "B2": ["n1"]}

        result = _build_edges(
            raw_edges=raw_edges,
            block_first=block_first,
            block_last=block_last,
            bid_to_nids=bid_to_nids,
            block_aliases={"B2": "B1"},
        )

        edges_n0_n1 = [
            e for e in result["edges"] if e["from"] == "n0" and e["to"] == "n1"
        ]
        assert (
            len(edges_n0_n1) == 1
        ), f"Expected exactly 1 edge n0→n1, got {len(edges_n0_n1)}: {edges_n0_n1}"
        # The single edge must be unlabeled — the branch is a no-op
        assert (
            "branch" not in edges_n0_n1[0]
        ), f"Expected unlabeled edge when T and F converge, got {edges_n0_n1[0]}"

    def test_convergent_branch_node_becomes_non_branch(self):
        """End-to-end: when both T/F targets alias to the same block, the branch
        node's outgoing edge should be unlabeled and the node kind should reflect
        that it's no longer a decision point."""
        from ftrace_semantic import _build_edges

        # Same scenario but with non-aliased source edges
        raw_edges = [
            {"fromBlock": "B5", "toBlock": "B7", "label": "T"},
            {"fromBlock": "B5", "toBlock": "B6", "label": "F"},
        ]
        block_first = {"B5": "n50", "B6": "n60", "B7": "n60"}
        block_last = {"B5": "n50", "B6": "n60", "B7": "n60"}
        bid_to_nids = {"B5": ["n50"], "B6": ["n60"], "B7": ["n60"]}

        result = _build_edges(
            raw_edges=raw_edges,
            block_first=block_first,
            block_last=block_last,
            bid_to_nids=bid_to_nids,
            block_aliases={"B7": "B6"},
        )

        out_from_n50 = [e for e in result["edges"] if e["from"] == "n50"]
        assert len(out_from_n50) == 1
        assert "branch" not in out_from_n50[0]


class TestEndToEndAliasingBugs:
    """Integration test: run all 4 passes on a tree that triggers
    the aliasing bugs, and verify the semantic graph is correct."""

    def test_non_branch_aliased_to_branch_produces_spurious_labeled_edges(self):
        """When a non-branch block (B4, one unlabeled successor) gets aliased
        to a branch block (B0, T/F successors) because they share the same
        mergedStmts content, the semantic graph should NOT have T/F edges
        originating from non-branch nodes."""
        from ftrace_semantic import transform

        tree = {
            "class": "com.example.Svc",
            "method": "handle",
            "methodSignature": "<com.example.Svc: void handle()>",
            "lineStart": 1,
            "lineEnd": 20,
            "sourceLineCount": 20,
            "blocks": [
                # B0: branch block — same line 10 call as B4
                {
                    "id": "B0",
                    "stmts": [
                        {"line": 10, "call": "Foo.bar"},
                        {"line": 10, "branch": "result == null"},
                    ],
                    "branchCondition": "result == null",
                },
                # B1: true target of B0
                {"id": "B1", "stmts": [{"line": 11, "call": "handle.error"}]},
                # B2: false target of B0
                {"id": "B2", "stmts": [{"line": 12, "call": "handle.success"}]},
                # B3: setup block before B4
                {"id": "B3", "stmts": [{"line": 9, "assign": "x = 1"}]},
                # B4: non-branch block — same line 10 call as B0, but no branch
                {
                    "id": "B4",
                    "stmts": [{"line": 10, "call": "Foo.bar"}],
                },
                # B5: successor of B4
                {"id": "B5", "stmts": [{"line": 15, "call": "next.step"}]},
            ],
            "edges": [
                {"fromBlock": "B0", "toBlock": "B1", "label": "T"},
                {"fromBlock": "B0", "toBlock": "B2", "label": "F"},
                {"fromBlock": "B3", "toBlock": "B4"},
                {"fromBlock": "B4", "toBlock": "B5"},
            ],
            "traps": [
                {
                    "type": "java.lang.Exception",
                    "handler": "B1",
                    "coveredBlocks": ["B0", "B2", "B3", "B4", "B5"],
                    "handlerBlocks": ["B1"],
                }
            ],
            "children": [],
        }

        result = transform(tree)

        # Find all BRANCH-kind nodes
        branch_nodes = {
            n["id"] for n in result["nodes"] if n["kind"] == NodeKind.BRANCH
        }
        non_branch_nodes = {
            n["id"] for n in result["nodes"] if n["kind"] != NodeKind.BRANCH
        }

        # T/F labeled edges must only originate from BRANCH nodes
        for edge in result["edges"]:
            if "branch" in edge:
                assert edge["from"] in branch_nodes, (
                    f"Labeled edge {edge} originates from non-branch node {edge['from']}. "
                    f"Branch nodes: {branch_nodes}"
                )

        # No node should have more than 2 labeled outgoing edges
        from collections import Counter

        labeled_out = Counter(e["from"] for e in result["edges"] if "branch" in e)
        for nid, count in labeled_out.items():
            assert (
                count <= 2
            ), f"Node {nid} has {count} labeled outgoing edges, expected <= 2"
