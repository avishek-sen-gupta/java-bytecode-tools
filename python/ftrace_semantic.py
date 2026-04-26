"""Transform raw xtrace JSON into semantic graph JSON.

Four composable passes, each a pure function tree → tree:
1. merge_stmts     — deduplicate block stmts by line
2. assign_clusters — assign blocks to trap clusters
3. deduplicate_blocks — alias identical blocks within clusters
4. build_semantic_graph — emit nodes/edges/clusters, drop raw fields
"""

from functools import reduce

from ftrace_types import MergedStmt, RawStmt


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
