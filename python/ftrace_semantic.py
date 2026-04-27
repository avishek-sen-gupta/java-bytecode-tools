"""Transform raw xtrace JSON into semantic graph JSON.

Four composable passes, each a pure function tree → tree:
1. merge_stmts     — deduplicate block stmts by line
2. assign_clusters — assign blocks to trap clusters
3. deduplicate_blocks — alias identical blocks within clusters
4. build_semantic_graph — emit nodes/edges/clusters, drop raw fields
"""

from collections import Counter
from functools import reduce

from ftrace_types import (
    ClusterAssignment,
    ClusterRole,
    BranchLabel,
    ExceptionEdge,
    MergedStmt,
    MethodSemanticCFG,
    NodeKind,
    RawBlock,
    RawStmt,
    RawTrap,
    SemanticCluster,
    SemanticEdge,
    SemanticNode,
    SourceTraceEntry,
    MethodCFG,
)

# --- Field-name constants (raw-tree dict keys) ---
_F_BLOCKS = "blocks"
_F_EDGES = "edges"
_F_TRAPS = "traps"
_F_METADATA = "metadata"
_F_SOURCE_TRACE = "sourceTrace"
_F_CHILDREN = "children"
_F_MERGED_SOURCE_TRACE = "mergedSourceTrace"
_F_CLUSTER_ASSIGNMENT = "clusterAssignment"
_F_BLOCK_ALIASES = "blockAliases"

# --- Domain type aliases ---
BlockId = str
NodeId = str


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


def merge_source_trace(source_trace: list[SourceTraceEntry]) -> list[MergedStmt]:
    """Deduplicate sourceTrace by line number, merging calls and branches."""
    by_line: dict[int, MergedStmt] = {}
    for entry in source_trace:
        line = entry["line"]
        if line < 0:
            continue
        if line not in by_line:
            by_line[line] = {"line": line, "calls": [], "branches": [], "assigns": []}
        for c in entry.get("calls", []):
            if c not in by_line[line]["calls"]:
                by_line[line]["calls"].append(c)
        if "branch" in entry:
            by_line[line]["branches"].append(entry["branch"])
    return [by_line[ln] for ln in sorted(by_line)]


def _is_leaf_node(node: MethodCFG) -> bool:
    """Check if a node is a leaf (ref, cycle, or filtered)."""
    return bool(node.get("ref") or node.get("cycle") or node.get("filtered"))


def merge_stmts_pass(tree: MethodCFG) -> MethodCFG:
    """Pass 1: Add mergedStmts to each block, or mergedSourceTrace. Returns new tree."""
    if _is_leaf_node(tree):
        return dict(tree)

    result = dict(tree)

    if "blocks" in tree:
        result["blocks"] = [
            {**block, "mergedStmts": merge_block_stmts(block.get("stmts", []))}
            for block in tree["blocks"]
        ]
    elif "sourceTrace" in tree:
        metadata = {
            **result.get("metadata", {}),
            "mergedSourceTrace": merge_source_trace(tree["sourceTrace"]),
        }
        result["metadata"] = metadata

    if "children" in tree:
        result["children"] = [merge_stmts_pass(child) for child in tree["children"]]

    return result


def assign_trap_clusters(
    traps: list[RawTrap],
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
        acc: dict[str, ClusterAssignment], indexed_trap: tuple[int, RawTrap]
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


def assign_clusters_pass(tree: MethodCFG) -> MethodCFG:
    """Pass 2: Add clusterAssignment to each method node. Returns new tree."""
    if _is_leaf_node(tree):
        return dict(tree)

    result = dict(tree)

    if "traps" in tree:
        metadata = {
            **result.get("metadata", {}),
            "clusterAssignment": assign_trap_clusters(tree.get("traps", [])),
        }
        result["metadata"] = metadata

    if "children" in tree:
        result["children"] = [assign_clusters_pass(child) for child in tree["children"]]

    return result


def block_content_signature(block: RawBlock) -> str:
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
    blocks: list[RawBlock],
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


def deduplicate_blocks_pass(tree: MethodCFG) -> MethodCFG:
    """Pass 3: Add blockAliases to each method node. Returns new tree."""
    if _is_leaf_node(tree):
        return dict(tree)

    result = dict(tree)

    if "blocks" in tree:
        cluster_assignment = tree.get("metadata", {}).get("clusterAssignment", {})
        aliases = compute_block_aliases(tree.get("blocks", []), cluster_assignment)
        metadata = {**result.get("metadata", {}), "blockAliases": aliases}
        result["metadata"] = metadata

    if "children" in tree:
        result["children"] = [
            deduplicate_blocks_pass(child) for child in tree["children"]
        ]

    return result


def short_class(fqcn: str) -> str:
    """Extract short class name from fully qualified name."""
    return fqcn.rsplit(".", 1)[-1]


def make_node_label(entry: MergedStmt) -> list[str]:
    """Build a label list for a merged stmt entry."""
    parts = [f"L{entry['line']}"]
    for c in sorted(entry.get("calls", [])):
        parts.append(
            short_class(c.rsplit(".", 1)[0]) + "." + c.rsplit(".", 1)[-1]
            if "." in c
            else c
        )
    if not entry.get("calls"):
        for a in entry.get("assigns", []):
            parts.append(a)
    return parts


def classify_node_kind(entry: MergedStmt) -> NodeKind:
    """Determine the node kind from a merged stmt entry."""
    if entry.get("branches"):
        return NodeKind.BRANCH
    if entry.get("calls"):
        return NodeKind.CALL
    if entry.get("assigns"):
        return NodeKind.ASSIGN
    return NodeKind.PLAIN


def build_semantic_graph_pass(tree: MethodCFG, next_id: int = 0) -> MethodSemanticCFG:
    """Pass 4: Build semantic graph from enriched tree. Returns new tree.

    Consumes blocks, traps, mergedStmts, clusterAssignment, blockAliases.
    Emits nodes, edges, clusters, exceptionEdges. Drops raw fields.

    next_id: starting node ID counter (for unique IDs across the tree).
    Returns the transformed tree. The caller can read the highest node ID
    from the nodes to continue numbering for children.
    """
    if _is_leaf_node(tree):
        return dict(tree)

    # sourceTrace fallback — no blocks, just a linear list of lines
    tree_metadata = tree.get("metadata", {})
    if "mergedSourceTrace" in tree_metadata and "blocks" not in tree:
        merged = tree_metadata["mergedSourceTrace"]
        node_counter = next_id
        all_nodes: list[SemanticNode] = []
        all_edges: list[SemanticEdge] = []
        for entry in merged:
            nid = f"n{node_counter}"
            node_counter += 1
            all_nodes.append(
                {
                    "id": nid,
                    "lines": [entry["line"]],
                    "kind": classify_node_kind(entry),
                    "label": make_node_label(entry),
                }
            )
        all_edges = [
            {"from": all_nodes[i]["id"], "to": all_nodes[i + 1]["id"]}
            for i in range(len(all_nodes) - 1)
        ]

        drop_fields = {"sourceTrace", "metadata"}
        result = {
            k: v for k, v in tree.items() if k not in drop_fields and k != "children"
        }
        result["nodes"] = all_nodes
        result["edges"] = all_edges
        result["clusters"] = []
        result["exceptionEdges"] = []
        if all_nodes:
            result["entryNodeId"] = all_nodes[0]["id"]
        if "children" in tree:
            result["children"] = [
                build_semantic_graph_pass(child, node_counter + i * 100)
                for i, child in enumerate(tree["children"])
            ]
        return result

    blocks = tree.get("blocks", [])
    raw_edges = tree.get("edges", [])
    traps = tree.get("traps", [])
    cluster_assignment = tree_metadata.get("clusterAssignment", {})
    block_aliases = tree_metadata.get("blockAliases", {})

    # --- Build nodes ---
    node_counter = next_id
    block_first: dict[str, str] = {}  # block_id → first node_id
    block_last: dict[str, str] = {}  # block_id → last node_id
    bid_to_nids: dict[str, list[str]] = {}  # block_id → list of node_ids
    all_nodes: list[SemanticNode] = []

    for block in blocks:
        bid = block["id"]

        # Aliased blocks share the canonical block's nodes
        if bid in block_aliases:
            canonical = block_aliases[bid]
            block_first[bid] = block_first[canonical]
            block_last[bid] = block_last[canonical]
            bid_to_nids[bid] = bid_to_nids[canonical]
            continue

        merged = block.get("mergedStmts", [])
        if not merged:
            nid = f"n{node_counter}"
            node_counter += 1
            all_nodes.append(
                {
                    "id": nid,
                    "lines": [],
                    "kind": NodeKind.PLAIN,
                    "label": [bid],
                }
            )
            block_first[bid] = nid
            block_last[bid] = nid
            bid_to_nids[bid] = [nid]
            continue

        nids_for_block: list[str] = []
        is_branch_block = bool(block.get("branchCondition"))

        for idx, entry in enumerate(merged):
            nid = f"n{node_counter}"
            node_counter += 1
            is_last = idx == len(merged) - 1

            kind = classify_node_kind(entry)
            label = make_node_label(entry)

            # Last node in a branch block includes the condition
            if is_branch_block and is_last:
                kind = NodeKind.BRANCH
                cond = block.get("branchCondition", "")
                if cond:
                    label.append(cond)

            all_nodes.append(
                {
                    "id": nid,
                    "lines": [entry["line"]],
                    "kind": kind,
                    "label": label,
                }
            )
            nids_for_block.append(nid)

            if bid not in block_first:
                block_first[bid] = nid

        block_last[bid] = nids_for_block[-1]
        bid_to_nids[bid] = nids_for_block

    # --- Build intra-block edges (sequential within a block) ---
    canonical_bids = [b["id"] for b in blocks if b["id"] not in block_aliases]
    all_edges: list[SemanticEdge] = [
        {"from": nids[i], "to": nids[i + 1]}
        for bid in canonical_bids
        for nids in [bid_to_nids.get(bid, [])]
        for i in range(len(nids) - 1)
    ]

    # --- Build inter-block edges (CFG edges) ---
    # Track shared nodes for reverse-edge artifact detection
    nid_block_count = Counter(block_first[bid] for bid in block_first)
    shared_nids = frozenset(nid for nid, c in nid_block_count.items() if c > 1)

    emitted: set[tuple[str, str, str]] = set()

    for raw_edge in raw_edges:
        from_bid = raw_edge["fromBlock"]
        to_bid = raw_edge["toBlock"]
        tail_nid = block_last.get(from_bid, "")
        succ_nid = block_first.get(to_bid, "")
        if not tail_nid or not succ_nid or tail_nid == succ_nid:
            continue

        label = raw_edge.get("label", "")
        if label:
            key = (tail_nid, succ_nid, label)
            if key not in emitted:
                emitted.add(key)
                all_edges.append(
                    {"from": tail_nid, "to": succ_nid, "branch": BranchLabel(label)}
                )
        else:
            key = (tail_nid, succ_nid, "")
            reverse = (succ_nid, tail_nid, "")
            if reverse in emitted and (
                tail_nid in shared_nids or succ_nid in shared_nids
            ):
                continue
            if key not in emitted:
                emitted.add(key)
                all_edges.append({"from": tail_nid, "to": succ_nid})

    # --- Build clusters ---
    all_clusters: list[SemanticCluster] = []
    exception_edges: list[ExceptionEdge] = []

    for i, trap in enumerate(traps):
        etype = short_class(trap["type"])

        try_bids = blocks_for_cluster(cluster_assignment, ClusterRole.TRY, i)
        handler_bids = blocks_for_cluster(cluster_assignment, ClusterRole.HANDLER, i)

        try_nids = [nid for bid in try_bids for nid in bid_to_nids.get(bid, [])]
        handler_nids = [nid for bid in handler_bids for nid in bid_to_nids.get(bid, [])]

        all_clusters.append(
            {
                "trapType": etype,
                "role": ClusterRole.TRY,
                "nodeIds": try_nids,
            }
        )

        handler_cluster: SemanticCluster = {
            "trapType": etype,
            "role": ClusterRole.HANDLER,
            "nodeIds": handler_nids,
        }
        handler_entry_nid = block_first.get(trap["handler"], "")
        if handler_entry_nid:
            handler_cluster["entryNodeId"] = handler_entry_nid
        all_clusters.append(handler_cluster)

        # Exception edge
        if handler_entry_nid:
            src_nid = (
                block_first.get(try_bids[0], "")
                if try_bids
                else next(
                    (
                        block_first[cb]
                        for cb in trap.get("coveredBlocks", [])
                        if cb in block_first
                    ),
                    "",
                )
            )
            if src_nid:
                exception_edges.append(
                    {
                        "from": src_nid,
                        "to": handler_entry_nid,
                        "trapType": etype,
                        "fromCluster": len(all_clusters) - 2,  # try cluster index
                        "toCluster": len(all_clusters) - 1,  # handler cluster index
                    }
                )

    # --- Assemble result ---
    # Drop raw/intermediate fields, keep tree metadata
    drop_fields = {
        "blocks",
        "edges",
        "traps",
        "metadata",
        "sourceTrace",
    }
    result = {k: v for k, v in tree.items() if k not in drop_fields and k != "children"}
    result["nodes"] = all_nodes
    result["edges"] = all_edges
    result["clusters"] = all_clusters
    result["exceptionEdges"] = exception_edges

    # Set entryNodeId for cross-cluster call edges from parent
    if all_nodes:
        result["entryNodeId"] = all_nodes[0]["id"]

    # Recurse into children
    if "children" in tree:
        result["children"] = [
            build_semantic_graph_pass(child, node_counter + i * 100)
            for i, child in enumerate(tree["children"])
        ]

    return result


def transform(tree: MethodCFG) -> MethodSemanticCFG:
    """Run all four passes on a tree."""
    enriched = reduce(
        lambda acc, fn: fn(acc),
        [merge_stmts_pass, assign_clusters_pass, deduplicate_blocks_pass],
        tree,
    )
    return build_semantic_graph_pass(enriched)


def main():
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Transform raw xtrace JSON into semantic graph JSON."
    )
    parser.add_argument("--input", type=Path, help="Input JSON file (default: stdin)")
    parser.add_argument(
        "--output", type=Path, help="Output JSON file (default: stdout)"
    )
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            tree = json.load(f)
    else:
        tree = json.load(sys.stdin)

    result = transform(tree)
    output = json.dumps(result, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote semantic graph to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
