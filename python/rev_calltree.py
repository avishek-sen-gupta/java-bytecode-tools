#!/usr/bin/env python3
"""
frames — backward call chain finder. Given a target class+line, find all call chains
that reach that method and emit a flat {nodes, calls, metadata} graph.

Usage:
  frames --call-graph <path> --to-class <FQCN> --to-line <n>
         [--from-class <FQCN>] [--from-line <n>]
         [--max-depth <n>] [--max-chains <n>]
"""

import argparse
import json
import re
import sys
from pathlib import Path

from node_types import NodeType


def extract_class(sig: str) -> str:
    m = re.match(r"<([^:]+):", sig)
    return m.group(1) if m else ""


def extract_method(sig: str) -> str:
    m = re.match(r"<[^:]+:[^)]+\b(\w+)\(", sig)
    return m.group(1) if m else ""


def find_target_sig(cls: str, line: int, method_lines: dict[str, dict]) -> str:
    """Return the sig of the method in cls whose [line_start, line_end] contains line."""
    return next(
        (
            sig
            for sig, lr in method_lines.items()
            if extract_class(sig) == cls
            and lr.get("line_start", -1) <= line <= lr.get("line_end", -1)
        ),
        "",
    )


def build_reverse_map(callees: dict[str, list[str]]) -> dict[str, list[str]]:
    """Invert callees → callers: {callee-sig: [caller-sig, ...]}."""
    result: dict[str, list[str]] = {}
    for caller, callee_list in callees.items():
        for callee in callee_list:
            result.setdefault(callee, []).append(caller)
    return result


def bfs_backward(
    target_sig: str,
    callers_map: dict[str, list[str]],
    max_depth: int,
    stop_at: str = "",
) -> set[str]:
    """BFS backward from target_sig up to max_depth hops.

    Returns the set of reachable caller sigs (not including target_sig itself).
    If stop_at is given, that sig is included but its callers are not explored.
    """
    reachable: set[str] = set()
    frontier = {target_sig}
    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for sig in frontier:
            for caller in callers_map.get(sig, []):
                if caller not in reachable and caller != target_sig:
                    reachable.add(caller)
                    if caller != stop_at:
                        next_frontier.add(caller)
        if not next_frontier:
            break
        frontier = next_frontier
    return reachable


def _dfs_chains(
    sig: str,
    target_sig: str,
    reachable: set[str],
    callees: dict[str, list[str]],
    path: list[str],
    results: list[list[str]],
    max_chains: int,
) -> None:
    if len(results) >= max_chains:
        return
    if sig == target_sig:
        results.append(list(path))
        return
    for callee in callees.get(sig, []):
        if callee == target_sig or callee in reachable:
            _dfs_chains(
                callee,
                target_sig,
                reachable,
                callees,
                path + [callee],
                results,
                max_chains,
            )
            if len(results) >= max_chains:
                return


def enumerate_chains(
    target_sig: str,
    reachable: set[str],
    callees: dict[str, list[str]],
    max_chains: int,
) -> list[list[str]]:
    """Enumerate distinct root→target chains via DFS. Roots = reachable sigs with no callers in reachable."""
    roots = [
        sig
        for sig in reachable
        if not any(sig in callees.get(other, []) for other in reachable)
    ]
    results: list[list[str]] = []
    for root in sorted(roots):
        if len(results) >= max_chains:
            break
        _dfs_chains(root, target_sig, reachable, callees, [root], results, max_chains)
    return results


def _node_entry(sig: str, method_lines: dict[str, dict]) -> dict:
    cls = extract_class(sig)
    method = extract_method(sig)
    base: dict = {
        "node_type": NodeType.JAVA_METHOD,
        "class": cls,
        "method": method,
        "methodSignature": sig,
    }
    lr = method_lines.get(sig, {})
    if lr:
        line_start = lr.get("line_start", 0)
        line_end = lr.get("line_end", 0)
        base["lineStart"] = line_start
        base["lineEnd"] = line_end
        base["sourceLineCount"] = max(0, line_end - line_start + 1)
    return base


def build_frames_graph(
    chains: list[list[str]],
    callsites: dict[str, dict[str, int]],
    method_lines: dict[str, dict],
) -> tuple[dict[str, dict], list[dict]]:
    """Build flat nodes+calls from a list of [root, ..., target] sig chains."""
    all_sigs = {sig for chain in chains for sig in chain}
    nodes: dict[str, dict] = {sig: _node_entry(sig, method_lines) for sig in all_sigs}
    calls: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()

    for chain in chains:
        for i in range(len(chain) - 1):
            caller = chain[i]
            callee = chain[i + 1]
            if (caller, callee) not in seen_edges:
                seen_edges.add((caller, callee))
                callsite_line = callsites.get(caller, {}).get(callee, 0)
                edge: dict = {"from": caller, "to": callee, "edge_info": {}}
                if callsite_line > 0:
                    edge["callSiteLine"] = callsite_line
                calls.append(edge)

    return nodes, calls


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--call-graph", "-g", type=Path, required=True, metavar="PATH")
    parser.add_argument("--to-class", required=True, metavar="FQCN")
    parser.add_argument("--to-line", required=True, type=int, metavar="N")
    parser.add_argument("--from-class", default="", metavar="FQCN")
    parser.add_argument("--from-line", default=0, type=int, metavar="N")
    parser.add_argument("--max-depth", default=20, type=int, metavar="N")
    parser.add_argument("--max-chains", default=50, type=int, metavar="N")
    args = parser.parse_args()

    with open(args.call_graph) as f:
        cg_data: dict = json.load(f)

    callees: dict[str, list[str]] = cg_data.get("callees", cg_data)
    callsites: dict[str, dict[str, int]] = cg_data.get("callsites", {})
    method_lines: dict[str, dict] = cg_data.get("methodLines", {})

    target_sig = find_target_sig(args.to_class, args.to_line, method_lines)
    if not target_sig:
        print(
            f"ERROR: no method in '{args.to_class}' contains line {args.to_line}",
            file=sys.stderr,
        )
        sys.exit(1)

    stop_at = ""
    if args.from_class:
        stop_at = find_target_sig(args.from_class, args.from_line, method_lines)
        if not stop_at:
            print(
                f"ERROR: no method in '{args.from_class}' contains line {args.from_line}",
                file=sys.stderr,
            )
            sys.exit(1)

    callers_map = build_reverse_map(callees)
    reachable = bfs_backward(target_sig, callers_map, args.max_depth, stop_at)

    if not reachable:
        print(
            f"ERROR: no callers found for '{target_sig}' within depth {args.max_depth}",
            file=sys.stderr,
        )
        sys.exit(1)

    chains = enumerate_chains(target_sig, reachable, callees, args.max_chains)

    if not chains:
        print(f"ERROR: could not enumerate chains to '{target_sig}'", file=sys.stderr)
        sys.exit(1)

    nodes, calls = build_frames_graph(chains, callsites, method_lines)

    metadata: dict = {
        "tool": "rev-calltree",
        "toClass": args.to_class,
        "toLine": args.to_line,
    }
    if args.from_class:
        metadata["fromClass"] = args.from_class
        metadata["fromLine"] = args.from_line

    json.dump(
        {"nodes": nodes, "calls": calls, "metadata": metadata}, sys.stdout, indent=2
    )
    print()


if __name__ == "__main__":
    main()
