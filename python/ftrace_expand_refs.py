#!/usr/bin/env python3
"""Expand ref nodes in a sliced trace using a pre-built ref index.

Pure function: uses frozenset for cycle detection (no mutation).
"""

import argparse
import json
import sys
from pathlib import Path

from typing import cast

from ftrace_types import MethodCFG


def expand_refs(
    node: MethodCFG, index: dict[str, MethodCFG], path: frozenset[str] = frozenset()
) -> MethodCFG:
    """Return a copy of node with ref nodes replaced by their full expansion.

    Args:
        node: trace node (may have ref=True)
        index: methodSignature -> full node mapping
        path: visited signatures for cycle detection (immutable)
    """
    if node.get("ref", False):
        return _expand_ref_node(node, index, path)

    sig = node.get("methodSignature", "")
    new_path = path | {sig} if sig else path

    if "children" not in node:
        return cast(MethodCFG, dict(node))

    return cast(
        MethodCFG,
        {
            **node,
            "children": [expand_refs(c, index, new_path) for c in node["children"]],
        },
    )


def _expand_ref_node(
    node: MethodCFG, index: dict[str, MethodCFG], path: frozenset[str]
) -> MethodCFG:
    """Expand a single ref node if its signature is in the index and not cyclic."""
    sig = node.get("methodSignature", "")

    if not sig or sig not in index or sig in path:
        return cast(MethodCFG, dict(node))

    full = index[sig]
    return cast(
        MethodCFG,
        {
            **{k: v for k, v in full.items() if k != "ref" and k != "children"},
            **(
                {}
                if "callSiteLine" not in node
                else {"callSiteLine": node["callSiteLine"]}
            ),
            "children": [
                expand_refs(c, index, path | {sig}) for c in full.get("children", [])
            ],
        },
    )


def main():
    parser = argparse.ArgumentParser(
        description="Expand ref nodes in a sliced trace using a pre-built ref index."
    )
    parser.add_argument("--input", type=Path, help="SlicedTrace JSON (default: stdin)")
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    data = json.loads(args.input.read_text()) if args.input else json.load(sys.stdin)

    expanded = expand_refs(data["trace"], data["refIndex"])

    output = json.dumps(expanded, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote expanded trace to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
