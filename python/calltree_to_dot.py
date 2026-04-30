"""Render calltree/frames {nodes, calls} output as a Graphviz call tree.

Pipeline:
  calltree ... | calltree-to-dot [--svg] [-o out.svg]
  frames  ...  | calltree-to-dot [--svg] [-o out.svg]
"""

import re

from ftrace_types import short_class

NodeSig = str
Edge = tuple[NodeSig, NodeSig]


def collect_nodes_flat(nodes: dict[str, dict]) -> frozenset[NodeSig]:
    """Return all node sigs from the flat nodes dict."""
    return frozenset(nodes.keys())


def collect_edges_flat(
    calls: list[dict],
) -> tuple[frozenset[Edge], frozenset[Edge]]:
    """Split calls into (normal_edges, cycle_edges), dropping filtered entries."""
    normal = frozenset(
        (c["from"], c["to"])
        for c in calls
        if not c.get("filtered") and not c.get("cycle")
    )
    cycle = frozenset((c["from"], c["to"]) for c in calls if c.get("cycle"))
    return normal, cycle


def find_roots(node_sigs: frozenset[NodeSig], calls: list[dict]) -> frozenset[NodeSig]:
    """Nodes with no incoming normal (non-filtered, non-cycle) call edges."""
    has_incoming = frozenset(
        c["to"] for c in calls if not c.get("filtered") and not c.get("cycle")
    )
    return node_sigs - has_incoming


def _make_dot_label(node: dict) -> str:
    return short_class(node.get("class", "?")) + "." + node.get("method", "?")


def _sanitize_id(sig: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", sig)


def render_dot(
    node_sigs: frozenset[NodeSig],
    edges: frozenset[Edge],
    cycle_edges: frozenset[Edge],
    label_map: dict[NodeSig, str],
    roots: frozenset[NodeSig] = frozenset(),
) -> str:
    node_lines = [
        f'  {_sanitize_id(sig)} [label="{label_map.get(sig, sig)}" shape={"ellipse" if sig in roots else "box"}];'
        for sig in sorted(node_sigs)
    ]
    edge_lines = [
        f"  {_sanitize_id(src)} -> {_sanitize_id(dst)};" for src, dst in sorted(edges)
    ]
    cycle_lines = [
        f"  {_sanitize_id(src)} -> {_sanitize_id(dst)} [style=dashed color=gray];"
        for src, dst in sorted(cycle_edges)
    ]
    body = "\n".join(node_lines + edge_lines + cycle_lines)
    return f"digraph calltree {{\n  rankdir=LR;\n{body}\n}}\n"


def main() -> None:
    import argparse
    import json
    import subprocess
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Render calltree/frames output as a Graphviz call graph."
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

    nodes: dict[str, dict] = data.get("nodes", {})
    calls: list[dict] = data.get("calls", [])

    node_sigs = collect_nodes_flat(nodes)
    edges, cycle_edges = collect_edges_flat(calls)
    roots = find_roots(node_sigs, calls)
    label_map = {sig: _make_dot_label(nd) for sig, nd in nodes.items()}
    dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

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
