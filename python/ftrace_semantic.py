"""Transform raw xtrace JSON into semantic graph JSON.

Four composable passes, each a pure function tree → tree:
1. merge_stmts     — deduplicate block stmts by line
2. assign_clusters — assign blocks to trap clusters
3. deduplicate_blocks — alias identical blocks within clusters
4. build_semantic_graph — emit nodes/edges/clusters, drop raw fields
"""

from functools import reduce

from ftrace_types import ClusterAssignment, ClusterRole, MergedStmt, RawStmt


def _accumulate_stmt(acc: dict[int, MergedStmt], s: RawStmt) -> dict[int, MergedStmt]:
    """Fold a single raw stmt into the accumulator, keyed by line number."""
    line = s["line"]
    if line < 0:
        return acc
    entry = acc.get(line, {"line": line, "calls": [], "branches": [], "assigns": []})
    return {
        **acc,
        line: {
            **entry,
            "calls": entry["calls"] + ([s["call"]] if "call" in s else []),
            "branches": entry["branches"] + ([s["branch"]] if "branch" in s else []),
            "assigns": entry["assigns"] + ([s["assign"]] if "assign" in s else []),
        },
    }


def merge_block_stmts(stmts: list[RawStmt]) -> list[MergedStmt]:
    """Deduplicate stmts by line number, aggregating calls/branches/assigns."""
    by_line = reduce(_accumulate_stmt, stmts, {})
    return [by_line[ln] for ln in sorted(by_line)]


def _is_leaf_node(node: dict) -> bool:
    """Check if a node is a leaf (ref, cycle, or filtered)."""
    return bool(node.get("ref") or node.get("cycle") or node.get("filtered"))


def merge_stmts_pass(tree: dict) -> dict:
    """Pass 1: Add mergedStmts to each block in the tree. Returns new tree."""
    if _is_leaf_node(tree):
        return dict(tree)

    result = dict(tree)

    if "blocks" in tree:
        result["blocks"] = [
            {**block, "mergedStmts": merge_block_stmts(block.get("stmts", []))}
            for block in tree["blocks"]
        ]

    if "children" in tree:
        result["children"] = [merge_stmts_pass(child) for child in tree["children"]]

    return result


def assign_trap_clusters(
    traps: list[dict],
) -> dict[str, ClusterAssignment]:
    """Assign each block to exactly one trap cluster.

    Handler membership takes priority over coverage. A block can be both
    a coveredBlock (for a finally/outer trap) and a handlerBlock (for a
    catch/inner trap). Handler wins.
    """
    all_handler_bids: frozenset[str] = frozenset(
        bid for trap in traps for bid in trap.get("handlerBlocks", [])
    )

    def _fold_trap(
        acc: dict[str, ClusterAssignment], indexed_trap: tuple[int, dict]
    ) -> dict[str, ClusterAssignment]:
        i, trap = indexed_trap
        covered = {
            bid: {"kind": ClusterRole.TRY, "trapIndex": i}
            for bid in trap.get("coveredBlocks", [])
            if bid not in all_handler_bids and bid not in acc
        }
        handlers = {
            bid: {"kind": ClusterRole.HANDLER, "trapIndex": i}
            for bid in trap.get("handlerBlocks", [])
            if bid not in acc and bid not in covered
        }
        return {**acc, **covered, **handlers}

    return reduce(_fold_trap, enumerate(traps), {})


def blocks_for_cluster(
    assignment: dict[str, ClusterAssignment], kind: str, trap_index: int
) -> list[str]:
    """Return block IDs assigned to a specific cluster, in insertion order."""
    return [
        bid
        for bid, a in assignment.items()
        if a["kind"] == kind and a["trapIndex"] == trap_index
    ]


def assign_clusters_pass(tree: dict) -> dict:
    """Pass 2: Add clusterAssignment to each method node. Returns new tree."""
    if _is_leaf_node(tree):
        return dict(tree)

    result = dict(tree)

    if "traps" in tree:
        result["clusterAssignment"] = assign_trap_clusters(tree.get("traps", []))

    if "children" in tree:
        result["children"] = [assign_clusters_pass(child) for child in tree["children"]]

    return result


def block_content_signature(block: dict) -> str:
    """Compute a content signature for a block based on mergedStmts and branchCondition.

    Two blocks with the same signature are visually identical and can be aliased.
    """
    entries = tuple(
        (
            entry["line"],
            tuple(sorted(entry.get("calls", []))),
            tuple(entry.get("branches", [])),
        )
        for entry in block.get("mergedStmts", [])
    )
    return str((entries, block.get("branchCondition", "")))


def compute_block_aliases(
    blocks: list[dict],
    cluster_assignment: dict[str, ClusterAssignment],
) -> dict[str, str]:
    """Find duplicate blocks within the same cluster.

    Returns a map of alias_block_id → canonical_block_id.
    Only blocks assigned to the same (kind, trapIndex) cluster are compared.
    """
    cluster_sigs: dict[tuple[str, int], dict[str, str]] = {}
    aliases: dict[str, str] = {}

    for block in blocks:
        bid = block["id"]
        if bid not in cluster_assignment:
            continue
        assignment = cluster_assignment[bid]
        cluster_key = (assignment["kind"], assignment["trapIndex"])
        sig = block_content_signature(block)

        sigs = cluster_sigs.setdefault(cluster_key, {})
        if sig in sigs:
            aliases[bid] = sigs[sig]
        else:
            sigs[sig] = bid

    return aliases


def deduplicate_blocks_pass(tree: dict) -> dict:
    """Pass 3: Add blockAliases to each method node. Returns new tree."""
    if _is_leaf_node(tree):
        return dict(tree)

    result = dict(tree)

    if "blocks" in tree:
        result["blockAliases"] = compute_block_aliases(
            tree.get("blocks", []),
            tree.get("clusterAssignment", {}),
        )

    if "children" in tree:
        result["children"] = [
            deduplicate_blocks_pass(child) for child in tree["children"]
        ]

    return result
