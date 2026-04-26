#!/usr/bin/env python3
"""Expand ref nodes in an ftrace subtree by looking up their full expansion in the original tree."""

import argparse
import json
import sys
from pathlib import Path


def index_full_tree(node: dict, index: dict[str, dict]):
    """Walk the full tree and index the first full expansion of each method signature."""
    sig = node.get("methodSignature")
    if (
        sig
        and not node.get("ref")
        and not node.get("cycle")
        and not node.get("filtered")
    ):
        if sig not in index:
            index[sig] = node
    for child in node.get("children", []):
        index_full_tree(child, index)


def expand_refs(node: dict, index: dict[str, dict], path: set[str]) -> dict:
    """Return a copy of node with ref nodes replaced by their full expansion."""
    if node.get("ref"):
        sig = node.get("methodSignature")
        if sig and sig in index and sig not in path:
            full = index[sig]
            expanded = {
                "callSiteLine": node.get("callSiteLine"),
                "class": full.get("class"),
                "method": full.get("method"),
                "methodSignature": sig,
                "lineStart": full.get("lineStart"),
                "lineEnd": full.get("lineEnd"),
                "sourceLineCount": full.get("sourceLineCount"),
                "sourceTrace": full.get("sourceTrace", []),
                "blocks": full.get("blocks", []),
                "children": [],
            }
            path.add(sig)
            for child in full.get("children", []):
                expanded["children"].append(expand_refs(child, index, path))
            path.discard(sig)
            return expanded
        return dict(node)

    result = dict(node)
    if "children" in node:
        sig = node.get("methodSignature", "")
        path.add(sig)
        result["children"] = [expand_refs(c, index, path) for c in node["children"]]
        path.discard(sig)
    return result


def count_refs(n):
    c = 1 if n.get("ref") else 0
    return c + sum(count_refs(ch) for ch in n.get("children", []))


def count_nodes(n):
    return 1 + sum(count_nodes(ch) for ch in n.get("children", []))


def main():
    parser = argparse.ArgumentParser(
        description="Expand ref nodes in a subtree using full expansions from the original tree."
    )
    parser.add_argument(
        "--subtree", required=True, type=Path, help="Subtree JSON to expand"
    )
    parser.add_argument(
        "--full-tree", required=True, type=Path, help="Full tree JSON for lookups"
    )
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    with open(args.subtree) as f:
        subtree = json.load(f)

    print(f"Loading full tree from {args.full_tree}...", file=sys.stderr)
    with open(args.full_tree) as f:
        full_tree = json.load(f)

    refs_before = count_refs(subtree)
    nodes_before = count_nodes(subtree)
    print(f"Subtree: {nodes_before} nodes, {refs_before} refs", file=sys.stderr)

    index: dict[str, dict] = {}
    index_full_tree(full_tree, index)
    print(f"Indexed {len(index)} unique method expansions", file=sys.stderr)

    expanded = expand_refs(subtree, index, set())

    refs_after = count_refs(expanded)
    nodes_after = count_nodes(expanded)
    print(
        f"Expanded: {nodes_after} nodes, {refs_after} refs remaining", file=sys.stderr
    )

    output = json.dumps(expanded, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
