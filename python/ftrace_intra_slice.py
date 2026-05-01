#!/usr/bin/env python3
"""Intra-procedural CFG slicer for ftrace output.

Takes an xtrace envelope, finds a target method by signature, and returns a
SlicedTrace containing only the CFG blocks that lie on a path between two
source lines (reachability-intersection algorithm).

Output format:
  { "trace": <sliced MethodCFG>, "refIndex": { methodSignature -> full node } }
"""

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from ftrace_slice import collect_ref_signatures
from ftrace_types import MethodCFG, RawBlock, RawBlockEdge, RawTrap, SourceTraceEntry


def blocks_containing_line(blocks: list[RawBlock], line: int) -> frozenset[str]:
    """Return block IDs whose stmts contain the given source line."""
    return frozenset(
        block["id"]
        for block in blocks
        if any(stmt["line"] == line for stmt in block.get("stmts", []))
    )


def forward_reachable(
    start_blocks: frozenset[str], edges: list[RawBlockEdge]
) -> frozenset[str]:
    """BFS forward from start_blocks through edges; return all reachable block IDs."""
    visited: set[str] = set(start_blocks)
    queue = list(start_blocks)
    while queue:
        current = queue.pop()
        for edge in edges:
            if edge["fromBlock"] == current and edge["toBlock"] not in visited:
                visited.add(edge["toBlock"])
                queue.append(edge["toBlock"])
    return frozenset(visited)


def backward_reachable(
    start_blocks: frozenset[str], edges: list[RawBlockEdge]
) -> frozenset[str]:
    """BFS backward from start_blocks through reversed edges; return all reaching block IDs."""
    visited: set[str] = set(start_blocks)
    queue = list(start_blocks)
    while queue:
        current = queue.pop()
        for edge in edges:
            if edge["toBlock"] == current and edge["fromBlock"] not in visited:
                visited.add(edge["fromBlock"])
                queue.append(edge["fromBlock"])
    return frozenset(visited)


def slice_blocks(blocks: list[RawBlock], kept: frozenset[str]) -> list[RawBlock]:
    """Return blocks whose id is in kept, preserving order."""
    return [block for block in blocks if block["id"] in kept]


def slice_edges(edges: list[RawBlockEdge], kept: frozenset[str]) -> list[RawBlockEdge]:
    """Return edges where both fromBlock and toBlock are in kept."""
    return [
        edge for edge in edges if edge["fromBlock"] in kept and edge["toBlock"] in kept
    ]


def slice_traps(traps: list[RawTrap], kept: frozenset[str]) -> list[RawTrap]:
    """Return traps with any block overlap with kept, trimming block lists to intersection."""
    result = []
    for trap in traps:
        covered = [b for b in trap["coveredBlocks"] if b in kept]
        handler_blocks = [b for b in trap["handlerBlocks"] if b in kept]
        if covered or handler_blocks:
            result.append(
                {
                    **trap,
                    "coveredBlocks": covered,
                    "handlerBlocks": handler_blocks,
                }
            )
    return result


def lines_in_kept_blocks(
    blocks: list[RawBlock], kept: frozenset[str]
) -> frozenset[int]:
    """Collect all source line numbers from blocks whose id is in kept."""
    return frozenset(
        stmt["line"]
        for block in blocks
        if block["id"] in kept
        for stmt in block.get("stmts", [])
    )


def slice_source_trace(
    source_trace: list[SourceTraceEntry], kept_lines: frozenset[int]
) -> list[SourceTraceEntry]:
    """Return source trace entries whose line is in kept_lines."""
    return [entry for entry in source_trace if entry["line"] in kept_lines]


def slice_children(
    children: list[MethodCFG], kept_lines: frozenset[int]
) -> list[MethodCFG]:
    """Return children whose callSiteLine is in kept_lines."""
    return [child for child in children if child.get("callSiteLine", -1) in kept_lines]


def intra_slice(cfg: MethodCFG, from_line: int, to_line: int) -> MethodCFG:
    """Slice a MethodCFG to blocks on paths between from_line and to_line.

    Uses reachability intersection: keeps blocks that are both
    forward-reachable from from_line's block AND backward-reachable from
    to_line's block.
    """
    blocks: list[RawBlock] = cfg.get("blocks", [])
    edges: list[RawBlockEdge] = cfg.get("edges", [])

    from_blocks = blocks_containing_line(blocks, from_line)
    to_blocks = blocks_containing_line(blocks, to_line)

    kept = forward_reachable(from_blocks, edges) & backward_reachable(to_blocks, edges)

    sliced_blocks = slice_blocks(blocks, kept)
    sliced_edges = slice_edges(edges, kept)
    sliced_traps = slice_traps(cfg.get("traps", []), kept)
    kept_lines = lines_in_kept_blocks(blocks, kept)
    sliced_source_trace = slice_source_trace(cfg.get("sourceTrace", []), kept_lines)
    sliced_children = slice_children(cfg.get("children", []), kept_lines)

    return {
        **cfg,
        "blocks": sliced_blocks,
        "edges": sliced_edges,
        "traps": sliced_traps,
        "sourceTrace": sliced_source_trace,
        "children": sliced_children,
    }


def _find_method(envelope: dict, method_sig: str) -> MethodCFG | None:
    """Search for method by signature in trace root then refIndex."""
    trace = cast(MethodCFG, envelope.get("trace", {}))
    if trace.get("methodSignature") == method_sig:
        return trace
    ref_index: dict[str, MethodCFG] = envelope.get("refIndex", {})
    return ref_index.get(method_sig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Intra-procedural CFG slice from an ftrace envelope."
    )
    parser.add_argument(
        "--input", type=Path, help="Input ftrace JSON file (default: stdin)"
    )
    parser.add_argument(
        "--method",
        required=True,
        metavar="SIG",
        help="methodSignature of the method to slice",
    )
    parser.add_argument(
        "--from-line",
        dest="from_line",
        type=int,
        required=True,
        metavar="N",
        help="Source line anchoring the slice start",
    )
    parser.add_argument(
        "--to-line",
        dest="to_line",
        type=int,
        required=True,
        metavar="N",
        help="Source line anchoring the slice end",
    )
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    raw_json = args.input.read_text() if args.input else sys.stdin.read()
    envelope = json.loads(raw_json)

    cfg = _find_method(envelope, args.method)
    if cfg is None:
        print(
            f"Error: method '{args.method}' not found in trace or refIndex.",
            file=sys.stderr,
        )
        sys.exit(1)

    blocks = cfg.get("blocks", [])
    if not blocks_containing_line(blocks, args.from_line):
        print(
            f"Error: --from-line {args.from_line} not found in any block.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not blocks_containing_line(blocks, args.to_line):
        print(
            f"Error: --to-line {args.to_line} not found in any block.", file=sys.stderr
        )
        sys.exit(1)

    sliced_cfg = intra_slice(cfg, args.from_line, args.to_line)

    if not sliced_cfg.get("blocks"):
        print(
            f"Error: no path between line {args.from_line} and line {args.to_line}.",
            file=sys.stderr,
        )
        sys.exit(1)

    ref_sigs = collect_ref_signatures(sliced_cfg)
    full_ref_index: dict[str, MethodCFG] = envelope.get("refIndex", {})
    ref_index = {sig: full_ref_index[sig] for sig in ref_sigs if sig in full_ref_index}

    output = json.dumps({"trace": sliced_cfg, "refIndex": ref_index}, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote intra-slice to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
