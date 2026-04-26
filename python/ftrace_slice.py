#!/usr/bin/env python3
"""Slice a subtree from an ftrace JSON and bundle a ref index for downstream expansion.

Output format (SlicedTrace):
  { "slice": <subtree>, "refIndex": { methodSignature -> full node } }

The refIndex is scoped: only signatures referenced by ref nodes in the slice are included.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from ftrace_types import TraceNode


def collect_ref_signatures(node: TraceNode) -> frozenset[str]:
    """Walk a subtree and return all methodSignature values where ref is true."""
    sig = node.get("methodSignature", "")
    refs = frozenset({sig}) if node.get("ref", False) and sig else frozenset()
    return refs | frozenset(
        s for child in node.get("children", []) for s in collect_ref_signatures(child)
    )


def index_full_tree(
    node: TraceNode, signatures: frozenset[str]
) -> dict[str, TraceNode]:
    """Walk the full tree, return {sig -> node} for signatures in the given set.

    First non-ref, non-cycle, non-filtered occurrence wins.
    Uses an internal accumulator for DFS first-occurrence semantics;
    the public interface is pure (fresh dict returned).
    """
    acc: dict[str, dict] = {}
    _index_walk(node, signatures, acc)
    return acc


def _index_walk(
    node: TraceNode, signatures: frozenset[str], acc: dict[str, TraceNode]
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


def main():
    parser = argparse.ArgumentParser(
        description="Slice a subtree using jq and bundle a ref index for expansion."
    )
    parser.add_argument(
        "--input", type=Path, help="Full ftrace JSON file (default: stdin)"
    )
    parser.add_argument(
        "--query",
        required=True,
        help="jq query to slice the subtree (e.g. '.children[0]')",
    )
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    # 1. Read the full tree (file or stdin)
    if args.input:
        if not args.input.exists():
            print(f"Error: {args.input} not found.", file=sys.stderr)
            sys.exit(1)
        raw_json = args.input.read_text()
    else:
        raw_json = sys.stdin.read()

    full_tree = json.loads(raw_json)

    # 2. Use jq to slice the target subtree
    try:
        result = subprocess.run(
            ["jq", args.query],
            input=raw_json,
            capture_output=True,
            text=True,
            check=True,
        )
        target = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"jq failed: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: jq query did not return valid JSON.", file=sys.stderr)
        sys.exit(1)

    if not isinstance(target, dict):
        print(
            "Error: jq query must return a single JSON object (node).",
            file=sys.stderr,
        )
        sys.exit(1)

    ref_sigs = collect_ref_signatures(target)
    ref_index = index_full_tree(full_tree, ref_sigs)

    # 3. Output SlicedTrace
    sliced_trace = {"slice": target, "refIndex": ref_index}
    output = json.dumps(sliced_trace, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote sliced trace to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
