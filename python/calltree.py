#!/usr/bin/env python3
"""
find-called-methods.py — given a class and method, emit an xtrace-format JSON
of all transitively reachable methods whose class name matches a regex.

Usage:
  find-called-methods.py --class <FQCN> --method <method> --pattern <regex>
                         --callgraph <path>

Options:
  --class      Fully-qualified class name of the entry point
  --method     Method name within that class
  --pattern    Regex — nodes whose class does not match (and have no matching
               descendants) are pruned from the tree
  --callgraph  Path to callgraph.json
"""

import argparse
import json
import re
import sys
from pathlib import Path


def extract_class(sig: str) -> str | None:
    m = re.match(r"<([^:]+):", sig)
    return m.group(1) if m else None


def extract_method(sig: str) -> str | None:
    m = re.match(r"<[^:]+:[^)]+\b(\w+)\(", sig)
    return m.group(1) if m else None


def build_line_index(dumps: list[dict]) -> dict[str, dict]:
    """Build a {signature: {lineStart, lineEnd}} index from parsed dump-*.json data."""
    return {
        method["signature"]: {
            "lineStart": method["lineStart"],
            "lineEnd": method["lineEnd"],
        }
        for dump in dumps
        for method in dump.get("methods", [])
    }


def annotate_tree(node: dict, line_index: dict[str, dict]) -> dict:
    """Return a new node tree with lineStart/lineEnd added from line_index."""
    sig = node.get("methodSignature", "")
    lines = line_index.get(sig, {})
    annotated_children = [
        annotate_tree(child, line_index) for child in node.get("children", [])
    ]
    return {**node, **lines, "children": annotated_children}


def build_tree(
    sig: str,
    cg: dict[str, list[str]],
    pat: re.Pattern,
    on_path: set[str],
    fully_built: dict[str, dict | None],
    ref_index: dict[str, dict],
) -> dict | None:
    cls = extract_class(sig)
    method = extract_method(sig)
    base: dict = {"class": cls, "method": method, "methodSignature": sig}

    if sig in on_path:
        return {**base, "cycle": True} if (cls and pat.search(cls)) else None

    if sig in fully_built:
        existing = fully_built[sig]
        if existing is None:
            return None
        ref_index[sig] = existing
        return {**base, "ref": True}

    on_path.add(sig)
    children = [
        child
        for callee in cg.get(sig, [])
        if (child := build_tree(callee, cg, pat, on_path, fully_built, ref_index))
        is not None
    ]
    on_path.remove(sig)

    if not (cls and pat.search(cls)) and not children:
        fully_built[sig] = None
        return None

    node = {**base, "children": children}
    fully_built[sig] = node
    return node


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--class", dest="cls", required=True, metavar="FQCN")
    parser.add_argument("--method", required=True)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--callgraph", "-g", type=Path, required=True, metavar="PATH")
    parser.add_argument(
        "--dump",
        type=Path,
        nargs="+",
        metavar="FILE",
        help="Dump JSON files to source line numbers from",
    )
    args = parser.parse_args()

    with open(args.callgraph) as f:
        cg: dict[str, list[str]] = json.load(f)

    entry_re = re.compile(rf"^<{re.escape(args.cls)}: .+\b{re.escape(args.method)}\(")
    entries = [sig for sig in cg if entry_re.match(sig)]

    if not entries:
        print(
            f"ERROR: method '{args.method}' not found in '{args.cls}'", file=sys.stderr
        )
        sys.exit(1)

    if len(entries) > 1:
        print(
            f"WARNING: multiple overloads found, using: {entries[0]}", file=sys.stderr
        )

    pat = re.compile(args.pattern)
    ref_index: dict[str, dict] = {}
    fully_built: dict[str, dict | None] = {}

    sys.setrecursionlimit(10000)
    trace = build_tree(entries[0], cg, pat, set(), fully_built, ref_index)

    if trace is None:
        print(
            f"ERROR: no methods matching '{args.pattern}' reachable from '{args.method}'",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.dump:
        dumps = [json.loads(p.read_text()) for p in args.dump]
        line_index = build_line_index(dumps)
        trace = annotate_tree(trace, line_index)
        ref_index = {
            sig: annotate_tree(node, line_index) for sig, node in ref_index.items()
        }

    json.dump({"trace": trace, "refIndex": ref_index}, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
