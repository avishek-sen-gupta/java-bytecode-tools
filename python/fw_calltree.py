#!/usr/bin/env python3
"""
calltree — given a class and method, emit a flat {nodes, calls, metadata} call graph
of all transitively reachable methods whose class name matches a regex.

Usage:
  calltree --class <FQCN> --method <method> --pattern <regex> --callgraph <path>
"""

import argparse
import json
import re
import sys
from pathlib import Path


def extract_class(sig: str) -> str:
    m = re.match(r"<([^:]+):", sig)
    return m.group(1) if m else ""


def extract_method(sig: str) -> str:
    m = re.match(r"<[^:]+:[^)]+\b(\w+)\(", sig)
    return m.group(1) if m else ""


def _node_entry(sig: str, method_lines: dict[str, dict]) -> dict[str, str | int]:
    cls = extract_class(sig)
    method = extract_method(sig)
    base: dict[str, str | int] = {
        "node_type": "java_method",
        "class": cls,
        "method": method,
        "methodSignature": sig,
    }
    lines = method_lines.get(sig, {})
    if lines:
        line_start = lines.get("lineStart", 0)
        line_end = lines.get("lineEnd", 0)
        base["lineStart"] = line_start
        base["lineEnd"] = line_end
        base["sourceLineCount"] = max(0, line_end - line_start + 1)
    return base


def build_graph(
    sig: str,
    cg: dict[str, list[str]],
    pat: re.Pattern,
    on_path: set[str],
    visited: set[str],
    nodes: dict[str, dict],
    calls: list[dict],
    callsites: dict[str, dict[str, int]],
    method_lines: dict[str, dict],
    caller_sig: str,
) -> bool:
    """DFS from sig, populating nodes and calls in place.

    Returns True if sig (or any descendant) matches pat — used to prune filtered subtrees.
    """
    cls = extract_class(sig)
    in_scope = bool(cls and pat.search(cls))

    if sig in on_path:
        # Cycle — emit a cycle edge, don't recurse
        callsite_line = callsites.get(caller_sig, {}).get(sig, 0) if caller_sig else 0
        edge: dict = {"from": caller_sig, "to": sig, "cycle": True, "edge_info": {}}
        if callsite_line > 0:
            edge["callSiteLine"] = callsite_line
        calls.append(edge)
        return in_scope

    if not in_scope:
        # Out of scope — emit filtered edge and stop
        if caller_sig:
            callsite_line = callsites.get(caller_sig, {}).get(sig, 0)
            edge = {"from": caller_sig, "to": sig, "filtered": True, "edge_info": {}}
            if callsite_line > 0:
                edge["callSiteLine"] = callsite_line
            calls.append(edge)
        return False

    # Emit caller→sig edge
    if caller_sig:
        callsite_line = callsites.get(caller_sig, {}).get(sig, 0)
        edge = {"from": caller_sig, "to": sig, "edge_info": {}}
        if callsite_line > 0:
            edge["callSiteLine"] = callsite_line
        calls.append(edge)

    # Already visited (but not on current path) — node already in nodes dict
    if sig in visited:
        return True

    visited.add(sig)
    nodes[sig] = _node_entry(sig, method_lines)

    on_path.add(sig)
    for callee in cg.get(sig, []):
        build_graph(
            callee,
            cg,
            pat,
            on_path,
            visited,
            nodes,
            calls,
            callsites,
            method_lines,
            sig,
        )
    on_path.remove(sig)

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--class", dest="cls", required=True, metavar="FQCN")
    parser.add_argument("--method", required=True)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--callgraph", "-g", type=Path, required=True, metavar="PATH")
    args = parser.parse_args()

    with open(args.callgraph) as f:
        cg_data: dict = json.load(f)

    cg: dict[str, list[str]] = cg_data.get("callees", cg_data)
    callsites: dict[str, dict[str, int]] = cg_data.get("callsites", {})
    method_lines: dict[str, dict] = cg_data.get("methodLines", {})

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
    nodes: dict[str, dict] = {}
    calls: list[dict] = []

    sys.setrecursionlimit(10000)
    found = build_graph(
        entries[0], cg, pat, set(), set(), nodes, calls, callsites, method_lines, ""
    )

    if not found:
        print(
            f"ERROR: no methods matching '{args.pattern}' reachable from '{args.method}'",
            file=sys.stderr,
        )
        sys.exit(1)

    output = {
        "nodes": nodes,
        "calls": calls,
        "metadata": {
            "tool": "calltree",
            "entryClass": args.cls,
            "entryMethod": args.method,
        },
    }
    json.dump(output, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
