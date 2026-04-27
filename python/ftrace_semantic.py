"""Transform raw xtrace JSON into semantic graph JSON.

Four composable passes, each a pure function tree → tree:
1. merge_stmts     — deduplicate block stmts by line
2. assign_clusters — assign blocks to trap clusters
3. deduplicate_blocks — alias identical blocks within clusters
4. build_semantic_graph — emit nodes/edges/clusters, drop raw fields
"""

from collections import Counter
from functools import reduce
from typing import TypedDict, cast

from ftrace_types import (
    ClusterAssignment,
    ClusterRole,
    BranchLabel,
    ExceptionEdge,
    MergedStmt,
    MethodSemanticCFG,
    NodeKind,
    RawBlock,
    RawBlockEdge,
    RawStmt,
    RawTrap,
    SemanticCluster,
    SemanticEdge,
    SemanticNode,
    SourceTraceEntry,
    MethodCFG,
    short_class,
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


# --- Internal TypedDicts for semantic graph builder communication ---


class _ResolvedInput(TypedDict):
    """Normalized inputs for the semantic graph builders."""

    blocks: list[RawBlock]
    edges: list[RawBlockEdge]
    traps: list[RawTrap]
    cluster_assignment: dict[BlockId, ClusterAssignment]
    block_aliases: dict[BlockId, BlockId]


class _NodeBuildResult(TypedDict):
    """Output of _build_nodes: semantic nodes plus block→node index maps."""

    nodes: list[SemanticNode]
    block_first: dict[BlockId, NodeId]
    block_last: dict[BlockId, NodeId]
    bid_to_nids: dict[BlockId, list[NodeId]]
    node_counter: int


class _EdgeBuildResult(TypedDict):
    """Output of _build_edges: all semantic edges (intra-block + inter-block)."""

    edges: list[SemanticEdge]


class _ClusterBuildResult(TypedDict):
    """Output of _build_clusters: clusters and exception edges."""

    clusters: list[SemanticCluster]
    exception_edges: list[ExceptionEdge]


def _resolve_inputs(tree: MethodCFG, tree_metadata: dict) -> _ResolvedInput:
    """Extract and normalize raw inputs for the semantic graph builders."""
    return {
        "blocks": tree.get(_F_BLOCKS, []),
        "edges": tree.get(_F_EDGES, []),
        "traps": tree.get(_F_TRAPS, []),
        "cluster_assignment": tree_metadata.get(_F_CLUSTER_ASSIGNMENT, {}),
        "block_aliases": tree_metadata.get(_F_BLOCK_ALIASES, {}),
    }


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


def _accumulate_source_trace(
    acc: dict[int, MergedStmt], entry: SourceTraceEntry
) -> dict[int, MergedStmt]:
    """Fold a single source trace entry into the accumulator, keyed by line number."""
    line = entry["line"]
    if line < 0:
        return acc
    existing = acc.get(line, {"line": line, "calls": [], "branches": [], "assigns": []})
    new_calls = [c for c in entry.get("calls", []) if c not in existing["calls"]]
    return {
        **acc,
        line: {
            **existing,
            "calls": existing["calls"] + new_calls,
            "branches": existing["branches"]
            + ([entry["branch"]] if "branch" in entry else []),
        },
    }


def merge_source_trace(source_trace: list[SourceTraceEntry]) -> list[MergedStmt]:
    """Deduplicate sourceTrace by line number, merging calls and branches."""
    by_line = reduce(_accumulate_source_trace, source_trace, {})
    return [by_line[ln] for ln in sorted(by_line)]


def _is_leaf_node(node: MethodCFG) -> bool:
    """Check if a node is a leaf (ref, cycle, or filtered)."""
    return bool(node.get("ref") or node.get("cycle") or node.get("filtered"))


def merge_stmts_pass(tree: MethodCFG) -> MethodCFG:
    """Pass 1: Add mergedStmts to each block, or mergedSourceTrace. Returns new tree."""
    if _is_leaf_node(tree):
        return cast(MethodCFG, dict(tree))

    result: dict = dict(tree)

    if "blocks" in tree:
        result["blocks"] = [
            {**block, "mergedStmts": merge_block_stmts(block.get("stmts", []))}
            for block in tree["blocks"]
        ]
    elif "sourceTrace" in tree:
        metadata: dict[str, object] = {
            **tree.get(_F_METADATA, {}),
            _F_MERGED_SOURCE_TRACE: merge_source_trace(tree["sourceTrace"]),
        }
        result[_F_METADATA] = metadata

    if "children" in tree:
        result["children"] = [merge_stmts_pass(child) for child in tree["children"]]

    return cast(MethodCFG, result)


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
        covered: dict[str, ClusterAssignment] = {
            bid: ClusterAssignment(kind=ClusterRole.TRY, trapIndex=i)
            for bid in trap.get("coveredBlocks", [])
            if bid not in all_handler_bids and bid not in acc
        }
        handlers: dict[str, ClusterAssignment] = {
            bid: ClusterAssignment(kind=ClusterRole.HANDLER, trapIndex=i)
            for bid in trap.get("handlerBlocks", [])
            if bid not in acc and bid not in covered
        }
        return {**acc, **covered, **handlers}

    initial: dict[str, ClusterAssignment] = {}
    return reduce(_fold_trap, enumerate(traps), initial)


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
        return cast(MethodCFG, dict(tree))

    result: dict = dict(tree)

    if "traps" in tree:
        metadata: dict[str, object] = {
            **tree.get(_F_METADATA, {}),
            _F_CLUSTER_ASSIGNMENT: assign_trap_clusters(tree.get("traps", [])),
        }
        result[_F_METADATA] = metadata

    if "children" in tree:
        result["children"] = [assign_clusters_pass(child) for child in tree["children"]]

    return cast(MethodCFG, result)


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


_AliasAcc = TypedDict(
    "_AliasAcc",
    {
        "sigs": dict[tuple[str, int], dict[str, str]],
        "aliases": dict[str, str],
    },
)


def _accumulate_alias(
    acc: _AliasAcc,
    block: RawBlock,
    cluster_assignment: dict[str, ClusterAssignment],
) -> _AliasAcc:
    """Fold a single block into the alias accumulator."""
    bid = block["id"]
    if bid not in cluster_assignment:
        return acc
    assignment = cluster_assignment[bid]
    cluster_key = (assignment["kind"], assignment["trapIndex"])
    sig = block_content_signature(block)
    cluster_sigs = acc["sigs"].get(cluster_key, {})

    if sig in cluster_sigs:
        return {
            "sigs": acc["sigs"],
            "aliases": {**acc["aliases"], bid: cluster_sigs[sig]},
        }
    return {
        "sigs": {**acc["sigs"], cluster_key: {**cluster_sigs, sig: bid}},
        "aliases": acc["aliases"],
    }


def compute_block_aliases(
    blocks: list[RawBlock],
    cluster_assignment: dict[str, ClusterAssignment],
) -> dict[str, str]:
    """Find duplicate blocks within the same cluster.

    Returns a map of alias_block_id → canonical_block_id.
    Only blocks assigned to the same (kind, trapIndex) cluster are compared.
    """
    result = reduce(
        lambda acc, block: _accumulate_alias(acc, block, cluster_assignment),
        blocks,
        _AliasAcc(sigs={}, aliases={}),
    )
    return result["aliases"]


def deduplicate_blocks_pass(tree: MethodCFG) -> MethodCFG:
    """Pass 3: Add blockAliases to each method node. Returns new tree."""
    if _is_leaf_node(tree):
        return cast(MethodCFG, dict(tree))

    result: dict = dict(tree)

    if "blocks" in tree:
        tree_metadata = tree.get(_F_METADATA, {})
        cluster_assignment = cast(
            dict[str, ClusterAssignment],
            tree_metadata.get(_F_CLUSTER_ASSIGNMENT, {}),
        )
        aliases = compute_block_aliases(tree.get("blocks", []), cluster_assignment)
        metadata: dict[str, object] = {
            **tree_metadata,
            _F_BLOCK_ALIASES: aliases,
        }
        result[_F_METADATA] = metadata

    if "children" in tree:
        result["children"] = [
            deduplicate_blocks_pass(child) for child in tree["children"]
        ]

    return cast(MethodCFG, result)


def _format_call(c: str) -> str:
    """Format a fully qualified call into ShortClass.method form."""
    return (
        short_class(c.rsplit(".", 1)[0]) + "." + c.rsplit(".", 1)[-1] if "." in c else c
    )


def make_node_label(entry: MergedStmt) -> list[str]:
    """Build a label list for a merged stmt entry."""
    calls = sorted(entry.get("calls", []))
    call_labels = [_format_call(c) for c in calls]
    assign_labels = list(entry.get("assigns", [])) if not calls else []
    return [f"L{entry['line']}"] + call_labels + assign_labels


def classify_node_kind(entry: MergedStmt) -> NodeKind:
    """Determine the node kind from a merged stmt entry."""
    if entry.get("branches"):
        return NodeKind.BRANCH
    if entry.get("calls"):
        return NodeKind.CALL
    if entry.get("assigns"):
        return NodeKind.ASSIGN
    return NodeKind.PLAIN


def _process_block_stmts(
    merged: list[MergedStmt],
    is_branch_block: bool,
    branch_condition: str,
    start_id: int,
) -> list[SemanticNode]:
    """Build semantic nodes for one block's merged statements."""
    last_idx = len(merged) - 1
    return [
        {
            "id": f"n{start_id + idx}",
            "lines": [entry["line"]],
            "kind": (
                NodeKind.BRANCH
                if is_branch_block and idx == last_idx
                else classify_node_kind(entry)
            ),
            "label": (
                make_node_label(entry)
                + ([branch_condition] if branch_condition else [])
                if is_branch_block and idx == last_idx
                else make_node_label(entry)
            ),
        }
        for idx, entry in enumerate(merged)
    ]


def _build_nodes(
    blocks: list[RawBlock], block_aliases: dict[BlockId, BlockId], next_id: int
) -> _NodeBuildResult:
    """Build semantic nodes from blocks. Pure function using reduce fold."""

    def fold_block(acc, block):
        nodes, first, last, bid_nids, counter = acc
        bid = block["id"]

        # Aliased blocks share the canonical block's nodes
        if bid in block_aliases:
            canonical = block_aliases[bid]
            return (
                nodes,
                {**first, bid: first[canonical]},
                {**last, bid: last[canonical]},
                {**bid_nids, bid: bid_nids[canonical]},
                counter,
            )

        merged = block.get("mergedStmts", [])

        # Empty block: placeholder node
        if not merged:
            nid = f"n{counter}"
            placeholder: SemanticNode = {
                "id": nid,
                "lines": [],
                "kind": NodeKind.PLAIN,
                "label": [bid],
            }
            return (
                [*nodes, placeholder],
                {**first, bid: nid},
                {**last, bid: nid},
                {**bid_nids, bid: [nid]},
                counter + 1,
            )

        # Normal block: build nodes from merged statements
        block_nodes = _process_block_stmts(
            merged,
            bool(block.get("branchCondition")),
            block.get("branchCondition", ""),
            counter,
        )
        nids = [n["id"] for n in block_nodes]
        return (
            [*nodes, *block_nodes],
            {**first, bid: nids[0]},
            {**last, bid: nids[-1]},
            {**bid_nids, bid: nids},
            counter + len(block_nodes),
        )

    all_nodes, block_first, block_last, bid_to_nids, node_counter = reduce(
        fold_block, blocks, ([], {}, {}, {}, next_id)
    )

    return {
        "nodes": all_nodes,
        "block_first": block_first,
        "block_last": block_last,
        "bid_to_nids": bid_to_nids,
        "node_counter": node_counter,
    }


def _build_intra_block_edges(
    bid_to_nids: dict[BlockId, list[NodeId]], block_aliases: dict[BlockId, BlockId]
) -> list[SemanticEdge]:
    """Build sequential edges within each canonical block."""
    return [
        {"from": nids[i], "to": nids[i + 1]}
        for bid, nids in bid_to_nids.items()
        if bid not in block_aliases
        for i in range(len(nids) - 1)
    ]


def _build_inter_block_edges(
    raw_edges: list[RawBlockEdge],
    block_first: dict[BlockId, NodeId],
    block_last: dict[BlockId, NodeId],
    block_aliases: dict[BlockId, BlockId],
) -> list[SemanticEdge]:
    """Build edges between blocks from raw CFG edges. Deduplicates and suppresses self-loops.

    Edges originating from aliased blocks are dropped — the canonical block's
    edges already cover the shared node. This prevents excess outgoing edges
    and conflicting labels when multiple blocks alias to the same canonical.
    """
    aliased_blocks = frozenset(block_aliases.keys())
    nid_block_count = Counter(nid for nid in block_first.values())
    shared_nids = frozenset(nid for nid, c in nid_block_count.items() if c > 1)

    def fold_edge(
        acc: tuple[list[SemanticEdge], dict[tuple[str, str], str]],
        raw_edge: RawBlockEdge,
    ) -> tuple[list[SemanticEdge], dict[tuple[str, str], str]]:
        edges, emitted = acc

        # Skip edges from aliased blocks — canonical block's edges suffice
        if raw_edge["fromBlock"] in aliased_blocks:
            return (edges, emitted)

        tail_nid = block_last.get(raw_edge["fromBlock"], "")
        succ_nid = block_first.get(raw_edge["toBlock"], "")
        if not tail_nid or not succ_nid or tail_nid == succ_nid:
            return (edges, emitted)

        key = (tail_nid, succ_nid)
        reverse = (succ_nid, tail_nid)
        label = raw_edge.get("label", "")

        if key in emitted:
            prev_label = emitted[key]
            # T and F converge to same target → branch is a no-op.
            # Replace the labeled edge with an unlabeled one.
            if label and prev_label and label != prev_label:
                unlabeled: SemanticEdge = {"from": tail_nid, "to": succ_nid}
                new_edges: list[SemanticEdge] = [
                    (unlabeled if e["from"] == tail_nid and e["to"] == succ_nid else e)
                    for e in edges
                ]
                return (new_edges, {**emitted, key: ""})
            return (edges, emitted)

        if label:
            return (
                [
                    *edges,
                    {"from": tail_nid, "to": succ_nid, "branch": BranchLabel(label)},
                ],
                {**emitted, key: label},
            )

        if reverse in emitted and (tail_nid in shared_nids or succ_nid in shared_nids):
            return (edges, emitted)
        return (
            [*edges, {"from": tail_nid, "to": succ_nid}],
            {**emitted, key: ""},
        )

    result_edges, _ = reduce(fold_edge, raw_edges, ([], {}))
    return result_edges


def _build_edges(
    raw_edges: list[RawBlockEdge],
    block_first: dict[BlockId, NodeId],
    block_last: dict[BlockId, NodeId],
    bid_to_nids: dict[BlockId, list[NodeId]],
    block_aliases: dict[BlockId, BlockId],
) -> _EdgeBuildResult:
    """Build all semantic edges: intra-block sequential + inter-block CFG."""
    intra = _build_intra_block_edges(bid_to_nids, block_aliases)
    inter = _build_inter_block_edges(raw_edges, block_first, block_last, block_aliases)
    return {"edges": [*intra, *inter]}


def _build_trap_clusters(
    trap_index: int,
    trap: RawTrap,
    cluster_assignment: dict[BlockId, ClusterAssignment],
    bid_to_nids: dict[BlockId, list[NodeId]],
    block_first: dict[BlockId, NodeId],
    cluster_offset: int,
) -> tuple[list[SemanticCluster], list[ExceptionEdge]]:
    """Build try + handler clusters and exception edge for one trap."""
    etype = short_class(trap["type"])

    try_bids = blocks_for_cluster(cluster_assignment, ClusterRole.TRY, trap_index)
    handler_bids = blocks_for_cluster(
        cluster_assignment, ClusterRole.HANDLER, trap_index
    )

    try_nids = [nid for bid in try_bids for nid in bid_to_nids.get(bid, [])]
    handler_nids = [nid for bid in handler_bids for nid in bid_to_nids.get(bid, [])]

    try_cluster: SemanticCluster = {
        "trapType": etype,
        "role": ClusterRole.TRY,
        "nodeIds": try_nids,
    }

    handler_entry_nid = block_first.get(trap["handler"], "")
    handler_cluster: SemanticCluster = cast(
        SemanticCluster,
        {
            "trapType": etype,
            "role": ClusterRole.HANDLER,
            "nodeIds": handler_nids,
            **({"entryNodeId": handler_entry_nid} if handler_entry_nid else {}),
        },
    )

    clusters = [try_cluster, handler_cluster]

    # Exception edge: try entry → handler entry
    src_nid = (
        (
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
        if handler_entry_nid
        else ""
    )
    ee = cast(
        ExceptionEdge,
        {
            "from": src_nid,
            "to": handler_entry_nid,
            "trapType": etype,
            "fromCluster": cluster_offset,
            "toCluster": cluster_offset + 1,
        },
    )
    exception_edges: list[ExceptionEdge] = [ee] if src_nid else []

    return (clusters, exception_edges)


def _build_clusters(
    traps: list[RawTrap],
    cluster_assignment: dict[BlockId, ClusterAssignment],
    bid_to_nids: dict[BlockId, list[NodeId]],
    block_first: dict[BlockId, NodeId],
) -> _ClusterBuildResult:
    """Build all clusters and exception edges from traps."""
    trap_results = [
        _build_trap_clusters(
            i, trap, cluster_assignment, bid_to_nids, block_first, i * 2
        )
        for i, trap in enumerate(traps)
    ]
    all_clusters = [c for clusters, _ in trap_results for c in clusters]
    all_exception_edges = [e for _, edges in trap_results for e in edges]
    return {"clusters": all_clusters, "exception_edges": all_exception_edges}


def build_semantic_graph_pass(tree: MethodCFG, next_id: int = 0) -> MethodSemanticCFG:
    """Pass 4: Build semantic graph from enriched tree. Returns new tree.

    Consumes blocks, traps, mergedStmts, clusterAssignment, blockAliases.
    Emits nodes, edges, clusters, exceptionEdges. Drops raw fields.

    next_id: starting node ID counter (for unique IDs across the tree).
    Returns the transformed tree. The caller can read the highest node ID
    from the nodes to continue numbering for children.
    """
    if _is_leaf_node(tree):
        return cast(MethodSemanticCFG, dict(tree))

    # sourceTrace fallback — no blocks, just a linear list of lines
    tree_metadata = tree.get(_F_METADATA, {})
    if _F_MERGED_SOURCE_TRACE in tree_metadata and _F_BLOCKS not in tree:
        merged = cast(list[MergedStmt], tree_metadata[_F_MERGED_SOURCE_TRACE])
        all_nodes: list[SemanticNode] = [
            {
                "id": f"n{next_id + i}",
                "lines": [entry["line"]],
                "kind": classify_node_kind(entry),
                "label": make_node_label(entry),
            }
            for i, entry in enumerate(merged)
        ]
        all_edges: list[SemanticEdge] = [
            {"from": all_nodes[i]["id"], "to": all_nodes[i + 1]["id"]}
            for i in range(len(all_nodes) - 1)
        ]
        node_counter = next_id + len(all_nodes)

        drop_fields = {_F_SOURCE_TRACE, _F_METADATA}
        result = {
            k: v for k, v in tree.items() if k not in drop_fields and k != _F_CHILDREN
        }
        result["nodes"] = all_nodes
        result["edges"] = all_edges
        result["clusters"] = []
        result["exceptionEdges"] = []
        if all_nodes:
            result["entryNodeId"] = all_nodes[0]["id"]
        if _F_CHILDREN in tree:
            result[_F_CHILDREN] = [
                build_semantic_graph_pass(child, node_counter + i * 100)
                for i, child in enumerate(tree[_F_CHILDREN])
            ]
        return cast(MethodSemanticCFG, result)

    # Resolve inputs from raw tree fields
    resolved = _resolve_inputs(tree, tree_metadata)

    # Build nodes: semantic nodes and block→node mappings
    node_build = _build_nodes(resolved["blocks"], resolved["block_aliases"], next_id)
    all_nodes = node_build["nodes"]
    block_first = node_build["block_first"]
    block_last = node_build["block_last"]
    bid_to_nids = node_build["bid_to_nids"]
    node_counter = node_build["node_counter"]

    # Build edges: intra-block and inter-block
    edge_build = _build_edges(
        resolved["edges"],
        block_first,
        block_last,
        bid_to_nids,
        resolved["block_aliases"],
    )
    all_edges = edge_build["edges"]

    # Build clusters: exception handling clusters and edges
    cluster_build = _build_clusters(
        resolved["traps"],
        resolved["cluster_assignment"],
        bid_to_nids,
        block_first,
    )
    all_clusters = cluster_build["clusters"]
    exception_edges = cluster_build["exception_edges"]

    # --- Assemble result ---
    # Drop raw/intermediate fields, keep tree metadata
    drop_fields = {
        _F_BLOCKS,
        _F_EDGES,
        _F_TRAPS,
        _F_METADATA,
        _F_SOURCE_TRACE,
    }
    result = {
        k: v for k, v in tree.items() if k not in drop_fields and k != _F_CHILDREN
    }
    result["nodes"] = all_nodes
    result["edges"] = all_edges
    result["clusters"] = all_clusters
    result["exceptionEdges"] = exception_edges

    # Set entryNodeId for cross-cluster call edges from parent
    if all_nodes:
        result["entryNodeId"] = all_nodes[0]["id"]

    # Recurse into children
    if _F_CHILDREN in tree:
        result[_F_CHILDREN] = [
            build_semantic_graph_pass(child, node_counter + i * 100)
            for i, child in enumerate(tree[_F_CHILDREN])
        ]

    return cast(MethodSemanticCFG, result)


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
