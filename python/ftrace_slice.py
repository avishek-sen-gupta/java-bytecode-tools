#!/usr/bin/env python3
"""
Slice and Expand: Use a jq query to find a node in an ftrace JSON,
then expand all its 'ref' nodes using the full tree as an index.
"""

import argparse
import json
import subprocess
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
            expanded = dict(full)
            expanded.pop("ref", None)
            if node.get("callSiteLine") is not None:
                expanded["callSiteLine"] = node["callSiteLine"]
            path.add(sig)
            expanded["children"] = [
                expand_refs(c, index, path) for c in full.get("children", [])
            ]
            path.discard(sig)
            return expanded
        return dict(node)

    result = dict(node)
    if "children" in node:
        sig = node.get("methodSignature", "")
        if sig:
            path.add(sig)
        result["children"] = [expand_refs(c, index, path) for c in node["children"]]
        if sig:
            path.discard(sig)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Slice a subtree using jq and expand all its refs in one go."
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="Full ftrace JSON file"
    )
    parser.add_argument(
        "--query",
        required=True,
        help="jq query to slice the subtree (e.g. '.children[0]')",
    )
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found.", file=sys.stderr)
        sys.exit(1)

    # 1. Use jq to slice the target subtree
    try:
        result = subprocess.run(
            ["jq", args.query, str(args.input)],
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
            "Error: jq query must return a single JSON object (node).", file=sys.stderr
        )
        sys.exit(1)

    # 2. Load and index the full tree for ref lookups
    with open(args.input) as f:
        full_tree = json.load(f)

    index: dict[str, dict] = {}
    index_full_tree(full_tree, index)

    # 3. Expand the sliced node
    expanded = expand_refs(target, index, set())

    # 4. Output
    output = json.dumps(expanded, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote sliced and expanded trace to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
