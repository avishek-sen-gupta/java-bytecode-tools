"""jspmap-to-dot — render a jspmap semantic-map JSON as Graphviz DOT / SVG / PNG."""

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Layer and node-type colours
# ---------------------------------------------------------------------------

_LAYER_COLOR: dict[str, str] = {
    "action": "#d4edda",  # green
    "service": "#f5f5dc",  # beige
    "dao": "#ffe0b2",  # orange
}
_LAYER_COLOR_DEFAULT = "white"
_JSP_COLOR = "#cce5ff"  # blue
_EL_COLOR = "#e8d5f5"  # purple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    node_id: str
    label: str
    color: str
    shape: str = "box"


@dataclass(frozen=True)
class Edge:
    from_id: str
    to_id: str


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _stable_id(prefix: str, key: str) -> str:
    """Return a stable, DOT-safe identifier for (prefix, key)."""
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return f"{prefix}_{h}"


def _short_class(fqcn: str) -> str:
    return fqcn.split(".")[-1]


def _jsp_node(jsp: str) -> Node:
    return Node(
        node_id=_stable_id("jsp", jsp),
        label=jsp,
        color=_JSP_COLOR,
        shape="folder",
    )


def _el_node(jsp: str, action: dict) -> Node:
    el = action["el"]
    ctx = action.get("el_context", {})
    tag, attr = ctx.get("tag", ""), ctx.get("attribute", "")
    context = f"{tag}@{attr}" if tag and tag != "_text" else "text"
    return Node(
        node_id=_stable_id("el", jsp + el),
        label=f"{el}\\n[{context}]",
        color=_EL_COLOR,
        shape="ellipse",
    )


def _hop_node(hop: dict) -> Node:
    label = f"{_short_class(hop['class'])}.{hop['method']}"
    color = _LAYER_COLOR.get(hop.get("layer", ""), _LAYER_COLOR_DEFAULT)
    return Node(
        node_id=_stable_id("hop", hop["signature"]),
        label=label,
        color=color,
    )


def _nodes_edges_for_action(
    action: dict,
) -> tuple[frozenset[Node], frozenset[Edge]]:
    jsp = action["jsp"]
    jsp_n = _jsp_node(jsp)
    el_n = _el_node(jsp, action)

    nodes: frozenset[Node] = frozenset([jsp_n, el_n])
    edges: frozenset[Edge] = frozenset([Edge(jsp_n.node_id, el_n.node_id)])

    for chain in action.get("chains", []):
        prev_id = el_n.node_id
        for hop in chain:
            hop_n = _hop_node(hop)
            nodes = nodes | {hop_n}
            edges = edges | {Edge(prev_id, hop_n.node_id)}
            prev_id = hop_n.node_id

    return nodes, edges


def _include_edges(data: dict, all_nodes: frozenset[Node]) -> frozenset[Edge]:
    jsp_includes: dict[str, list[str]] = data.get("meta", {}).get("jsp_includes", {})
    node_by_label: dict[str, str] = {n.label: n.node_id for n in all_nodes}
    return frozenset(
        Edge(node_by_label[parent], node_by_label[child])
        for parent, children in jsp_includes.items()
        for child in children
        if parent in node_by_label and child in node_by_label
    )


def build_graph(data: dict) -> tuple[frozenset[Node], frozenset[Edge]]:
    """Build de-duplicated node/edge sets from a jspmap JSON dict."""
    all_nodes: frozenset[Node] = frozenset()
    all_edges: frozenset[Edge] = frozenset()
    for action in data.get("actions", []):
        nodes, edges = _nodes_edges_for_action(action)
        all_nodes = all_nodes | nodes
        all_edges = all_edges | edges
    all_edges = all_edges | _include_edges(data, all_nodes)
    return all_nodes, all_edges


# ---------------------------------------------------------------------------
# DOT rendering
# ---------------------------------------------------------------------------


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _render_node(node: Node) -> str:
    label = _escape(node.label)
    return (
        f'  {node.node_id} [label="{label}", shape="{node.shape}", '
        f'style="filled,rounded", fillcolor="{node.color}"];'
    )


def _render_edge(edge: Edge) -> str:
    return f"  {edge.from_id} -> {edge.to_id};"


def build_dot(
    nodes: frozenset[Node],
    edges: frozenset[Edge],
    splines: str = "",
) -> str:
    """Render node/edge sets as a Graphviz DOT string."""
    header = [
        "digraph jspmap {",
        "  rankdir=TB;",
        *([f'  splines="{splines}";'] if splines else []),
        '  node [fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
        "",
    ]
    node_lines = sorted(_render_node(n) for n in nodes)
    edge_lines = sorted(_render_edge(e) for e in edges)
    footer = ["}"]
    return "\n".join([*header, *node_lines, "", *edge_lines, *footer])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render jspmap JSON as Graphviz DOT, SVG, or PNG."
    )
    parser.add_argument("--input", type=Path, help="jspmap JSON file (default: stdin)")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (.dot, .svg, or .png). Default: DOT to stdout.",
    )
    parser.add_argument(
        "--splines",
        default="",
        choices=["", "spline", "ortho", "curved", "line", "polyline"],
        help="Graphviz edge routing style (default: Graphviz default)",
    )
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text() if args.input else sys.stdin.read())
    nodes, edges = build_graph(data)
    dot = build_dot(nodes, edges, splines=args.splines)

    if not args.output:
        print(dot)
        return

    ext = args.output.suffix.lower()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if ext in (".svg", ".png"):
        fmt = ext.lstrip(".")
        result = subprocess.run(
            ["dot", f"-T{fmt}", "-o", str(args.output)],
            input=dot,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            print(f"dot failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        print(f"Rendered {args.output}", file=sys.stderr)
    else:
        args.output.write_text(dot)
        print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
