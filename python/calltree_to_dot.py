"""Render find-called-methods output as a Graphviz call tree.

Pipeline:
  find-called-methods ... | calltree-to-dot [--svg] [-o out.svg]

No ftrace-semantic step needed — this consumes the {trace, refIndex} envelope directly
and emits a DOT digraph: one node per method, one edge per caller→callee relationship.
"""

import re
from functools import reduce
from ftrace_types import MethodCFG, short_class

# --- Types ---

NodeSig = str
Edge = tuple[NodeSig, NodeSig]


# --- Pure functions ---


def _is_leaf(node: MethodCFG) -> bool:
    return bool(node.get("ref") or node.get("cycle") or node.get("filtered"))


def _resolve(node: MethodCFG, ref_index: dict[str, MethodCFG]) -> MethodCFG:
    """For a ref leaf, return the resolved full node from ref_index (or node itself)."""
    if node.get("ref"):
        sig = node.get("methodSignature", "")
        return ref_index.get(sig, node)
    return node


def collect_nodes(
    trace: MethodCFG, ref_index: dict[str, MethodCFG]
) -> frozenset[NodeSig]:
    """Collect all method signatures reachable from trace, resolving refs."""

    def _fold(acc: frozenset[NodeSig], node: MethodCFG) -> frozenset[NodeSig]:
        sig = node.get("methodSignature", "")
        if not sig or sig in acc:
            return acc
        acc = acc | frozenset({sig})
        resolved = _resolve(node, ref_index)
        if _is_leaf(resolved):
            return acc
        return reduce(_fold, resolved.get("children", []), acc)

    return _fold(frozenset(), trace)


def collect_edges(trace: MethodCFG, ref_index: dict[str, MethodCFG]) -> frozenset[Edge]:
    """Collect all (parent_sig, child_sig) edges reachable from trace, resolving refs."""

    def _fold(
        acc: tuple[frozenset[Edge], frozenset[NodeSig]], node: MethodCFG
    ) -> tuple[frozenset[Edge], frozenset[NodeSig]]:
        edges, visited = acc
        sig = node.get("methodSignature", "")
        if not sig or sig in visited:
            return acc
        visited = visited | frozenset({sig})
        resolved = _resolve(node, ref_index)
        if _is_leaf(resolved):
            return (edges, visited)
        children = resolved.get("children", [])
        new_edges = frozenset(
            (sig, child.get("methodSignature", ""))
            for child in children
            if child.get("methodSignature", "")
        )
        acc = (edges | new_edges, visited)
        return reduce(_fold, children, acc)

    result_edges, _ = _fold((frozenset(), frozenset()), trace)
    return result_edges


def make_dot_label(node: MethodCFG) -> str:
    """Return ShortClass.method label for a node."""
    return short_class(node.get("class", "?")) + "." + node.get("method", "?")


def _sanitize_id(sig: str) -> str:
    """Convert a method signature to a valid DOT node ID."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", sig)


def render_dot(
    nodes: frozenset[NodeSig],
    edges: frozenset[Edge],
    label_map: dict[NodeSig, str],
) -> str:
    """Emit a Graphviz DOT digraph string."""
    node_lines = [
        f'  {_sanitize_id(sig)} [label="{label_map.get(sig, sig)}" shape=box];'
        for sig in sorted(nodes)
    ]
    edge_lines = [
        f"  {_sanitize_id(src)} -> {_sanitize_id(dst)};" for src, dst in sorted(edges)
    ]
    body = "\n".join(node_lines + edge_lines)
    return f"digraph calltree {{\n  rankdir=LR;\n{body}\n}}\n"


# --- Entry point ---


def main() -> None:
    import argparse
    import json
    import subprocess
    import sys
    from pathlib import Path
    from typing import cast

    parser = argparse.ArgumentParser(
        description="Render find-called-methods output as a Graphviz call tree."
    )
    parser.add_argument("--input", type=Path, help="Input JSON (default: stdin)")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output file (default: stdout)"
    )
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--svg", action="store_true", help="Render to SVG via dot")
    fmt.add_argument("--png", action="store_true", help="Render to PNG via dot")
    args = parser.parse_args()

    data = (
        json.loads(Path(args.input).read_text()) if args.input else json.load(sys.stdin)
    )

    trace = cast(MethodCFG, data.get("trace", data))
    ref_index: dict[str, MethodCFG] = data.get("refIndex", {})

    nodes = collect_nodes(trace, ref_index)

    # Build label map: walk the tree once more to collect node dicts
    def _gather_node_dicts(
        acc: dict[NodeSig, MethodCFG], node: MethodCFG
    ) -> dict[NodeSig, MethodCFG]:
        sig = node.get("methodSignature", "")
        if not sig or sig in acc:
            return acc
        acc = {**acc, sig: node}
        resolved = _resolve(node, ref_index)
        if _is_leaf(resolved):
            return acc
        return reduce(_gather_node_dicts, resolved.get("children", []), acc)

    node_dicts = _gather_node_dicts({}, trace)
    label_map = {sig: make_dot_label(nd) for sig, nd in node_dicts.items()}

    edges = collect_edges(trace, ref_index)
    dot = render_dot(nodes, edges, label_map)

    if not args.svg and not args.png:
        if args.output:
            args.output.write_text(dot)
        else:
            print(dot, end="")
        return

    fmt_flag = "-Tsvg" if args.svg else "-Tpng"
    result = subprocess.run(
        ["dot", fmt_flag],
        input=dot,
        capture_output=True,
        text=(fmt_flag == "-Tsvg"),
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)

    if args.output:
        if fmt_flag == "-Tsvg":
            args.output.write_text(result.stdout)
        else:
            args.output.write_bytes(result.stdout)
    else:
        if fmt_flag == "-Tsvg":
            print(result.stdout, end="")
        else:
            sys.stdout.buffer.write(result.stdout)


if __name__ == "__main__":
    main()
