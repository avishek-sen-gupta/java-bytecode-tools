#!/usr/bin/env python3
"""Slice a subtree from an ftrace JSON and bundle a ref index for downstream expansion.

Output format (SlicedTrace):
  { "trace": <subtree>, "refIndex": { methodSignature -> full node } }

The refIndex is scoped: only signatures referenced by ref nodes in the slice are included.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from ftrace_types import MethodCFG


def collect_ref_signatures(node: MethodCFG) -> frozenset[str]:
    """Walk a subtree and return all methodSignature values where ref is true."""
    sig = node.get("methodSignature", "")
    refs = frozenset({sig}) if node.get("ref", False) and sig else frozenset()
    return refs | frozenset(
        s for child in node.get("children", []) for s in collect_ref_signatures(child)
    )


def index_full_tree(
    node: MethodCFG, signatures: frozenset[str]
) -> dict[str, MethodCFG]:
    """Walk the full tree, return {sig -> node} for signatures in the given set.

    First non-ref, non-cycle, non-filtered occurrence wins.
    Uses an internal accumulator for DFS first-occurrence semantics;
    the public interface is pure (fresh dict returned).
    """
    acc: dict[str, MethodCFG] = {}
    _index_walk(node, signatures, acc)
    return acc


def _index_walk(
    node: MethodCFG, signatures: frozenset[str], acc: dict[str, MethodCFG]
) -> None:
    """DFS walker for index_full_tree. Mutates acc (internal only)."""
    sig = node.get("methodSignature", "")
    if (
        sig
        and sig in signatures
        and sig not in acc
        and not node.get("ref", False)
        and not node.get("cycle", False)
        and not node.get("filtered", False)
    ):
        acc[sig] = node
    for child in node.get("children", []):
        _index_walk(child, signatures, acc)


def matches(node: MethodCFG, class_name: str, line: int) -> bool:
    """Return True if node matches the given class name and (if line > 0) contains that line.

    line == 0 means not provided — matches any line range for the class.
    lineStart/lineEnd are xtrace output fields present in JSON but not declared in TypedDict.
    """
    class_match = node.get("class", "") == class_name
    if line == 0:
        return class_match
    return class_match and node.get("lineStart", 0) <= line <= node.get("lineEnd", 0)


def find_subtree(tree: MethodCFG, class_name: str, line: int) -> list[MethodCFG]:
    """DFS search for first node matching class_name (+line). Returns [node] or []."""
    if matches(tree, class_name, line):
        return [tree]
    return next(
        (
            result
            for child in tree.get("children", [])
            for result in [find_subtree(child, class_name, line)]
            if result
        ),
        [],
    )


def prune_to_target(node: MethodCFG, class_name: str, line: int) -> list[MethodCFG]:
    """Return [node_with_pruned_children] if target is reachable, [] otherwise.

    When node itself matches target: return [node with children stripped].
    Multiple paths to target are preserved as a branching tree.
    """
    if matches(node, class_name, line):
        return [{**node, "children": []}]
    pruned_children = [
        pruned
        for child in node.get("children", [])
        for pruned in prune_to_target(child, class_name, line)
    ]
    if not pruned_children:
        return []
    return [{**node, "children": pruned_children}]


def main():
    parser = argparse.ArgumentParser(
        description="Slice a subtree from an ftrace and bundle a ref index for expansion."
    )
    parser.add_argument(
        "--input", type=Path, help="Full ftrace JSON file (default: stdin)"
    )
    parser.add_argument(
        "--from", dest="from_class", metavar="CLASS", help="FQCN of start node"
    )
    parser.add_argument(
        "--from-line",
        dest="from_line",
        type=int,
        default=0,
        metavar="N",
        help="Line within --from class to narrow match",
    )
    parser.add_argument(
        "--to", dest="to_class", metavar="CLASS", help="FQCN of target node"
    )
    parser.add_argument(
        "--to-line",
        dest="to_line",
        type=int,
        default=0,
        metavar="N",
        help="Line within --to class to narrow match",
    )
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    if not args.from_class and not args.to_class:
        parser.error("At least one of --from or --to must be provided.")

    # 1. Read the full tree (file or stdin)
    if args.input:
        if not args.input.exists():
            print(f"Error: {args.input} not found.", file=sys.stderr)
            sys.exit(1)
        raw_json = args.input.read_text()
    else:
        raw_json = sys.stdin.read()

    full_tree = json.loads(raw_json)

    # Unwrap envelope if present (xtrace outputs {trace, refIndex})
    is_envelope = (
        isinstance(full_tree, dict) and "trace" in full_tree and "refIndex" in full_tree
    )
    trace = cast(MethodCFG, full_tree["trace"] if is_envelope else full_tree)

    # 2. Navigate the trace tree according to mode
    if args.from_class and args.to_class:
        # --from + --to: find --from subtree, then prune to paths reaching --to
        from_results = find_subtree(trace, args.from_class, args.from_line)
        if not from_results:
            print(
                f"Error: no node found for --from {args.from_class} (line {args.from_line})",
                file=sys.stderr,
            )
            sys.exit(1)
        pruned = prune_to_target(from_results[0], args.to_class, args.to_line)
        if not pruned:
            print(
                f"Error: no path from {args.from_class} to {args.to_class}",
                file=sys.stderr,
            )
            sys.exit(1)
        target = pruned[0]
    elif args.from_class:
        # --from only: return subtree rooted at matching node
        from_results = find_subtree(trace, args.from_class, args.from_line)
        if not from_results:
            print(
                f"Error: no node found for --from {args.from_class} (line {args.from_line})",
                file=sys.stderr,
            )
            sys.exit(1)
        target = from_results[0]
    else:
        # --to only: prune from trace root to paths reaching --to
        pruned = prune_to_target(trace, args.to_class, args.to_line)
        if not pruned:
            print(
                f"Error: no path to --to {args.to_class} (line {args.to_line})",
                file=sys.stderr,
            )
            sys.exit(1)
        target = pruned[0]

    target = cast(MethodCFG, target)
    ref_sigs = collect_ref_signatures(target)

    # Extract refIndex from envelope if present, otherwise build it by walking the tree
    if isinstance(full_tree, dict) and "trace" in full_tree and "refIndex" in full_tree:
        # Input was an envelope: filter the existing refIndex by collected signatures
        full_index = full_tree["refIndex"]
        ref_index = {sig: full_index[sig] for sig in ref_sigs if sig in full_index}
    else:
        # Input was a plain trace: walk to build the refIndex
        ref_index = index_full_tree(cast(MethodCFG, full_tree), ref_sigs)

    # 3. Output SlicedTrace
    sliced_trace = {"trace": target, "refIndex": ref_index}
    output = json.dumps(sliced_trace, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote sliced trace to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
