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
    Violation,
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


class _ClusterPairResult(TypedDict):
    """Output of _build_cluster_pair: try/handler clusters and handler entry node."""

    try_cluster: SemanticCluster
    handler_cluster: SemanticCluster
    handler_entry_nid: NodeId
    try_bids: list[BlockId]


class _ResolvedEdge(TypedDict):
    """A raw edge resolved to node IDs with provenance."""

    from_nid: NodeId
    to_nid: NodeId
    label: str
    to_block: BlockId


class _GraphBuildResult(TypedDict):
    """Combined output of source-trace or blocks builder for assembly."""

    nodes: list[SemanticNode]
    edges: list[SemanticEdge]
    clusters: list[SemanticCluster]
    exception_edges: list[ExceptionEdge]
    node_counter: int


def _resolve_inputs(tree: MethodCFG, tree_metadata: dict) -> _ResolvedInput:
    """Extract and normalize raw inputs for the semantic graph builders."""
    return {
        "blocks": tree.get(_F_BLOCKS, []),
        "edges": tree.get(_F_EDGES, []),
        "traps": tree.get(_F_TRAPS, []),
        "cluster_assignment": tree_metadata.get(_F_CLUSTER_ASSIGNMENT, {}),
        "block_aliases": tree_metadata.get(_F_BLOCK_ALIASES, {}),
    }


def _accumulate_merged(
    acc: dict[int, MergedStmt],
    line: int,
    calls: list[str],
    branches: list[str],
    assigns: list[str],
) -> dict[int, MergedStmt]:
    """Fold one entry into the line-keyed accumulator, merging calls/branches/assigns."""
    if line < 0:
        return acc
    entry = acc.get(line, {"line": line, "calls": [], "branches": [], "assigns": []})
    return {
        **acc,
        line: {
            **entry,
            "calls": entry["calls"] + calls,
            "branches": entry["branches"] + branches,
            "assigns": entry["assigns"] + assigns,
        },
    }


def _accumulate_stmt(acc: dict[int, MergedStmt], s: RawStmt) -> dict[int, MergedStmt]:
    """Fold a single raw stmt into the accumulator, keyed by line number."""
    return _accumulate_merged(
        acc,
        s["line"],
        calls=[s["call"]] if "call" in s else [],
        branches=[s["branch"]] if "branch" in s else [],
        assigns=[s["assign"]] if "assign" in s else [],
    )


def merge_block_stmts(stmts: list[RawStmt]) -> list[MergedStmt]:
    """Deduplicate stmts by line number, aggregating calls/branches/assigns."""
    by_line = reduce(_accumulate_stmt, stmts, {})
    return [by_line[ln] for ln in sorted(by_line)]


def _accumulate_source_trace(
    acc: dict[int, MergedStmt], entry: SourceTraceEntry
) -> dict[int, MergedStmt]:
    """Fold a single source trace entry into the accumulator, keyed by line number."""
    existing_calls = acc.get(
        entry["line"], {"line": 0, "calls": [], "branches": [], "assigns": []}
    )["calls"]
    new_calls = [c for c in entry.get("calls", []) if c not in existing_calls]
    return _accumulate_merged(
        acc,
        entry["line"],
        calls=new_calls,
        branches=[entry["branch"]] if "branch" in entry else [],
        assigns=[],
    )


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


def _resolve_edge_triples(
    raw_edges: list[RawBlockEdge],
    block_first: dict[BlockId, NodeId],
    block_last: dict[BlockId, NodeId],
    aliased_blocks: frozenset[BlockId],
) -> list[_ResolvedEdge]:
    """Stage 1: Filter and resolve raw edges to (from_nid, to_nid, label, to_block) tuples.

    Drops edges from aliased blocks, missing nodes, and self-loops.
    """
    return [
        {
            "from_nid": block_last.get(e["fromBlock"], ""),
            "to_nid": block_first.get(e["toBlock"], ""),
            "label": e.get("label", ""),
            "to_block": e["toBlock"],
        }
        for e in raw_edges
        if e["fromBlock"] not in aliased_blocks
        and block_last.get(e["fromBlock"], "")
        and block_first.get(e["toBlock"], "")
        and block_last.get(e["fromBlock"], "") != block_first.get(e["toBlock"], "")
    ]


def _classify_group(group: list[_ResolvedEdge]) -> list[SemanticEdge]:
    """Classify a group of edges sharing the same (from, to) key."""
    from_nid, to_nid = group[0]["from_nid"], group[0]["to_nid"]
    if len(group) == 1:
        e = group[0]
        return (
            [{"from": from_nid, "to": to_nid, "branch": BranchLabel(e["label"])}]
            if e["label"]
            else [{"from": from_nid, "to": to_nid}]
        )
    to_blocks = frozenset(e["to_block"] for e in group)
    if len(to_blocks) == 1:
        # Natural convergence: same raw block → keep distinct labeled edges
        unique_labels = dict.fromkeys(e["label"] for e in group)
        return [
            (
                {"from": from_nid, "to": to_nid, "branch": BranchLabel(label)}
                if label
                else {"from": from_nid, "to": to_nid}
            )
            for label in unique_labels
        ]
    # Aliasing-induced convergence: different blocks → single unlabeled edge
    return [{"from": from_nid, "to": to_nid}]


def _classify_convergence(resolved_edges: list[_ResolvedEdge]) -> list[SemanticEdge]:
    """Stage 2: Group edges by (from, to) and classify natural vs aliasing convergence."""
    groups = reduce(
        lambda acc, e: {
            **acc,
            (e["from_nid"], e["to_nid"]): [
                *acc.get((e["from_nid"], e["to_nid"]), []),
                e,
            ],
        },
        resolved_edges,
        cast(dict[tuple[str, str], list[_ResolvedEdge]], {}),
    )
    return [edge for group in groups.values() for edge in _classify_group(group)]


def _suppress_reverse_edges(
    edges: list[SemanticEdge],
    shared_nids: frozenset[NodeId],
) -> list[SemanticEdge]:
    """Stage 3: Suppress reverse-direction unlabeled edges at shared nodes."""

    def fold(
        acc: tuple[list[SemanticEdge], frozenset[tuple[str, str]]],
        e: SemanticEdge,
    ) -> tuple[list[SemanticEdge], frozenset[tuple[str, str]]]:
        result, seen = acc
        key = (e["from"], e["to"])
        reverse = (e["to"], e["from"])
        if (
            "branch" not in e
            and reverse in seen
            and (e["from"] in shared_nids or e["to"] in shared_nids)
        ):
            return (result, seen | {key})
        return ([*result, e], seen | {key})

    result, _ = reduce(fold, edges, ([], frozenset()))
    return result


def _build_inter_block_edges(
    raw_edges: list[RawBlockEdge],
    block_first: dict[BlockId, NodeId],
    block_last: dict[BlockId, NodeId],
    block_aliases: dict[BlockId, BlockId],
) -> list[SemanticEdge]:
    """Build edges between blocks via 3-stage pipeline: resolve → classify → suppress."""
    aliased_blocks = frozenset(block_aliases.keys())
    nid_block_count = Counter(nid for nid in block_first.values())
    shared_nids = frozenset(nid for nid, c in nid_block_count.items() if c > 1)

    resolved = _resolve_edge_triples(raw_edges, block_first, block_last, aliased_blocks)
    classified = _classify_convergence(resolved)
    return _suppress_reverse_edges(classified, shared_nids)


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


def _build_cluster_pair(
    trap: RawTrap,
    trap_index: int,
    cluster_assignment: dict[BlockId, ClusterAssignment],
    bid_to_nids: dict[BlockId, list[NodeId]],
    block_first: dict[BlockId, NodeId],
) -> _ClusterPairResult:
    """Build try + handler cluster pair for one trap."""
    etype = short_class(trap["type"])

    try_bids = blocks_for_cluster(cluster_assignment, ClusterRole.TRY, trap_index)
    handler_bids = blocks_for_cluster(
        cluster_assignment, ClusterRole.HANDLER, trap_index
    )

    try_nids = [nid for bid in try_bids for nid in bid_to_nids.get(bid, [])]
    handler_nids = [nid for bid in handler_bids for nid in bid_to_nids.get(bid, [])]

    handler_entry_nid = block_first.get(trap["handler"], "")
    return {
        "try_cluster": {
            "trapType": etype,
            "role": ClusterRole.TRY,
            "nodeIds": try_nids,
        },
        "handler_cluster": cast(
            SemanticCluster,
            {
                "trapType": etype,
                "role": ClusterRole.HANDLER,
                "nodeIds": handler_nids,
                **({"entryNodeId": handler_entry_nid} if handler_entry_nid else {}),
            },
        ),
        "handler_entry_nid": handler_entry_nid,
        "try_bids": try_bids,
    }


def _resolve_exception_edge_source(
    try_bids: list[BlockId],
    trap: RawTrap,
    block_first: dict[BlockId, NodeId],
    handler_entry_nid: NodeId,
) -> NodeId:
    """Resolve the source node for an exception edge.

    Returns the first try block's entry node, falling back to the first
    covered block present in block_first. Returns "" if no handler entry.
    """
    if not handler_entry_nid:
        return ""
    if try_bids:
        return block_first.get(try_bids[0], "")
    return next(
        (block_first[cb] for cb in trap.get("coveredBlocks", []) if cb in block_first),
        "",
    )


def _build_exception_edge(
    src_nid: NodeId,
    handler_entry_nid: NodeId,
    etype: str,
    cluster_offset: int,
) -> list[ExceptionEdge]:
    """Build exception edge from source to handler entry. Returns [] if no source."""
    if not src_nid:
        return []
    return [
        cast(
            ExceptionEdge,
            {
                "from": src_nid,
                "to": handler_entry_nid,
                "trapType": etype,
                "fromCluster": cluster_offset,
                "toCluster": cluster_offset + 1,
            },
        )
    ]


def _build_trap_clusters(
    trap_index: int,
    trap: RawTrap,
    cluster_assignment: dict[BlockId, ClusterAssignment],
    bid_to_nids: dict[BlockId, list[NodeId]],
    block_first: dict[BlockId, NodeId],
    cluster_offset: int,
) -> tuple[list[SemanticCluster], list[ExceptionEdge]]:
    """Build try + handler clusters and exception edge for one trap."""
    pair = _build_cluster_pair(
        trap, trap_index, cluster_assignment, bid_to_nids, block_first
    )
    src_nid = _resolve_exception_edge_source(
        pair["try_bids"], trap, block_first, pair["handler_entry_nid"]
    )
    exception_edges = _build_exception_edge(
        src_nid, pair["handler_entry_nid"], short_class(trap["type"]), cluster_offset
    )
    return ([pair["try_cluster"], pair["handler_cluster"]], exception_edges)


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


def _build_from_source_trace(
    merged: list[MergedStmt], next_id: int
) -> _GraphBuildResult:
    """Build a linear node chain from merged source trace entries."""
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
    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "clusters": [],
        "exception_edges": [],
        "node_counter": next_id + len(all_nodes),
    }


def _build_from_blocks(
    tree: MethodCFG, tree_metadata: dict, next_id: int
) -> _GraphBuildResult:
    """Build full CFG from blocks, edges, traps, and cluster assignments."""
    resolved = _resolve_inputs(tree, tree_metadata)

    node_build = _build_nodes(resolved["blocks"], resolved["block_aliases"], next_id)
    edge_build = _build_edges(
        resolved["edges"],
        node_build["block_first"],
        node_build["block_last"],
        node_build["bid_to_nids"],
        resolved["block_aliases"],
    )
    cluster_build = _build_clusters(
        resolved["traps"],
        resolved["cluster_assignment"],
        node_build["bid_to_nids"],
        node_build["block_first"],
    )
    return {
        "nodes": node_build["nodes"],
        "edges": edge_build["edges"],
        "clusters": cluster_build["clusters"],
        "exception_edges": cluster_build["exception_edges"],
        "node_counter": node_build["node_counter"],
    }


def _assemble_result(
    tree: MethodCFG,
    build_result: _GraphBuildResult,
    drop_fields: frozenset[str],
) -> MethodSemanticCFG:
    """Assemble final result dict: drop raw fields, add semantic fields, recurse children."""
    result = {
        k: v for k, v in tree.items() if k not in drop_fields and k != _F_CHILDREN
    }
    result["nodes"] = build_result["nodes"]
    result["edges"] = build_result["edges"]
    result["clusters"] = build_result["clusters"]
    result["exceptionEdges"] = build_result["exception_edges"]
    if build_result["nodes"]:
        result["entryNodeId"] = build_result["nodes"][0]["id"]
    if _F_CHILDREN in tree:
        node_counter = build_result["node_counter"]
        result[_F_CHILDREN] = [
            build_semantic_graph_pass(child, node_counter + i * 100)
            for i, child in enumerate(tree[_F_CHILDREN])
        ]
    return cast(MethodSemanticCFG, result)


_DROP_SOURCE_TRACE = frozenset({_F_SOURCE_TRACE, _F_METADATA})
_DROP_BLOCKS = frozenset({_F_BLOCKS, _F_EDGES, _F_TRAPS, _F_METADATA, _F_SOURCE_TRACE})


def build_semantic_graph_pass(tree: MethodCFG, next_id: int = 0) -> MethodSemanticCFG:
    """Pass 4: Build semantic graph from enriched tree. Returns new tree.

    Dispatches to _build_from_source_trace or _build_from_blocks,
    then assembles the result via _assemble_result.
    """
    if _is_leaf_node(tree):
        return cast(MethodSemanticCFG, dict(tree))

    tree_metadata = tree.get(_F_METADATA, {})
    if _F_MERGED_SOURCE_TRACE in tree_metadata and _F_BLOCKS not in tree:
        build_result = _build_from_source_trace(
            cast(list[MergedStmt], tree_metadata[_F_MERGED_SOURCE_TRACE]),
            next_id,
        )
        return _assemble_result(tree, build_result, _DROP_SOURCE_TRACE)

    return _assemble_result(
        tree, _build_from_blocks(tree, tree_metadata, next_id), _DROP_BLOCKS
    )


def transform(tree: MethodCFG) -> tuple[MethodSemanticCFG, list[Violation]]:
    """Run all four passes on a tree, then validate. Returns (result, violations)."""
    from ftrace_validate import validate_tree  # local to avoid circular import

    enriched = reduce(
        lambda acc, fn: fn(acc),
        [merge_stmts_pass, assign_clusters_pass, deduplicate_blocks_pass],
        tree,
    )
    result = build_semantic_graph_pass(enriched)
    violations = validate_tree(result)
    return (result, violations)


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
            data = json.load(f)
    else:
        data = json.load(sys.stdin)

    # Unwrap envelope if present (xtrace outputs {trace, refIndex})
    if isinstance(data, dict) and "trace" in data and "refIndex" in data:
        tree = cast(MethodCFG, data["trace"])
    else:
        tree = cast(MethodCFG, data)

    result, violations = transform(tree)

    # Log violations to stderr
    if violations:
        for v in violations:
            method = v["method"]
            node_id = v["node_id"]
            kind = v["kind"]
            message = v["message"]
            location = f"{method}:{node_id}" if node_id else method
            print(f"[{kind}] {location} — {message}", file=sys.stderr)

    output = json.dumps(result, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote semantic graph to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
