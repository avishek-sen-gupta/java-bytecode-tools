#!/usr/bin/env python3
"""Render semantic graph JSON as Graphviz DOT, then optionally produce SVG/PNG.

This is a dumb renderer: it reads the semantic JSON emitted by ftrace_semantic
and maps it to DOT syntax. All graph transformations (merging, clustering,
dedup) happen upstream in ftrace_semantic.
"""

import json
import sys
from pathlib import Path
from functools import reduce
from typing import TypedDict

from ftrace_types import (
    ExceptionEdge,
    MethodSemanticCFG,
    NodeKind,
    BranchLabel,
    SemanticCluster,
    SemanticEdge,
    SemanticNode,
)

# -- Visual constants --
NODE_STYLE: dict[NodeKind, dict[str, str]] = {
    NodeKind.PLAIN: {"shape": "box", "fillcolor": "white", "style": "filled,rounded"},
    NodeKind.CALL: {"shape": "box", "fillcolor": "#d4edda", "style": "filled,rounded"},
    NodeKind.BRANCH: {"shape": "diamond", "fillcolor": "#cce5ff", "style": "filled"},
    NodeKind.ASSIGN: {
        "shape": "box",
        "fillcolor": "#f5f5dc",
        "style": "filled,rounded",
    },
    NodeKind.CYCLE: {
        "shape": "box",
        "fillcolor": "#ffcccc",
        "style": "filled,rounded,dashed",
        "color": "red",
    },
    NodeKind.REF: {
        "shape": "box",
        "fillcolor": "#e8e8e8",
        "style": "filled,rounded,dashed",
        "color": "#999999",
    },
    NodeKind.FILTERED: {
        "shape": "box",
        "fillcolor": "#fff3cd",
        "style": "filled,rounded,dashed",
        "color": "#cc9900",
    },
}

BRANCH_COLORS: dict[BranchLabel, str] = {
    BranchLabel.T: "#28a745",
    BranchLabel.F: "#dc3545",
}


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def short_class(fqcn: str) -> str:
    return fqcn.rsplit(".", 1)[-1]


def _render_node(nid: str, node: SemanticNode) -> str:
    """Render a single semantic node as a DOT node statement."""
    label = r"\n".join(escape(p) for p in node["label"])
    kind = NodeKind(node["kind"])
    style = NODE_STYLE.get(kind, NODE_STYLE[NodeKind.PLAIN])
    attrs = f'label="{label}"'
    for k, v in style.items():
        attrs += f', {k}="{v}"'
    return f"    {nid} [" + attrs + "];"


def _render_edge(edge: SemanticEdge) -> str:
    """Render a single semantic edge as a DOT edge statement."""
    src, dst = edge["from"], edge["to"]
    branch = edge.get("branch", "")
    if branch:
        color = BRANCH_COLORS.get(BranchLabel(branch), "black")
        return (
            f"    {src} -> {dst} "
            f'[label="{branch}", color="{color}", fontcolor="{color}"];'
        )
    return f"    {src} -> {dst};"


def _render_exception_edge(ee: ExceptionEdge, clusters: list[SemanticCluster]) -> str:
    """Render an exception edge with ltail/lhead cluster references."""
    src, dst = ee["from"], ee["to"]
    trap_type = escape(ee["trapType"])
    attrs = (
        f'label="{trap_type}", color="#ffa500", style="dashed", ' f'fontcolor="#ffa500"'
    )
    from_idx = ee.get("fromCluster", -1)
    to_idx = ee.get("toCluster", -1)
    if from_idx >= 0 and clusters[from_idx].get("nodeIds", []):
        attrs += f', ltail="cluster_trap_{from_idx}"'
    if to_idx >= 0 and clusters[to_idx].get("nodeIds", []):
        attrs += f', lhead="cluster_trap_{to_idx}"'
    return f"    {src} -> {dst} [{attrs}];"


class _MethodDotResult(TypedDict):
    lines: list[str]
    cross_edges: list[str]
    next_counter: int
    entry_nid: str


def _render_leaf(node: MethodSemanticCFG, counter: int) -> tuple[list[str], str, int]:
    """Render a leaf node (ref/cycle/filtered). Returns (lines, nid, next_counter).

    Returns ([], "", counter) if node is not a leaf.
    """
    cls = short_class(node.get("class", "?"))
    method = node.get("method", "?")
    leaf_kind = next(
        (k for k in ("cycle", "ref", "filtered") if node.get(k, False)),
        "",
    )
    if not leaf_kind:
        return ([], "", counter)
    nid = f"n_leaf_{counter}"
    label = f"{cls}.{method}\\n({leaf_kind})"
    style = NODE_STYLE[NodeKind(leaf_kind)]
    attrs = f'label="{escape(label)}"'
    attrs += "".join(f', {k}="{v}"' for k, v in style.items())
    return ([f"  {nid} [{attrs}];"], nid, counter + 1)


def _render_trap_cluster(index: int, cluster: SemanticCluster) -> list[str]:
    """Render one trap cluster as a DOT subgraph."""
    trap_type = cluster["trapType"]
    role = cluster["role"]
    node_ids = cluster.get("nodeIds", [])

    tc_id = f"cluster_trap_{index}"
    header = [f"    subgraph {tc_id} {{"]

    if role == "try":
        style_lines = [
            f'      label="try ({escape(trap_type)})";',
            '      style="dashed,rounded"; color="#ffa500"; fontcolor="#ffa500";',
        ]
    else:
        h_label = (
            "finally"
            if trap_type.lower() in ("throwable", "any")
            else f"catch ({escape(trap_type)})"
        )
        style_lines = [
            f'      label="{h_label}";',
            '      style="dashed,rounded"; color="#007bff"; fontcolor="#007bff";',
        ]

    node_lines = [f"      {nid};" for nid in node_ids]
    return [*header, *style_lines, *node_lines, "    }"]


def _render_cross_edges(
    nodes: list[SemanticNode],
    children: list[MethodSemanticCFG],
    child_entries: list[str],
    entry_nid: str,
) -> list[str]:
    """Build parent→child call edges by matching callSiteLine to node lines."""
    line_to_nids: dict[int, list[str]] = reduce(
        lambda acc, pair: {**acc, pair[0]: [*acc.get(pair[0], []), pair[1]]},
        ((ln, n["id"]) for n in nodes for ln in n.get("lines", [])),
        {},
    )

    def _edge_for_child(child: MethodSemanticCFG, child_entry: str) -> list[str]:
        if not child_entry:
            return []
        csl = child.get("callSiteLine", -1)
        source_nids = line_to_nids.get(csl, [])
        if source_nids:
            return [
                f"  {source_nids[0]} -> {child_entry} "
                f'[color="#e05050", style=bold, penwidth=1.5];'
            ]
        if entry_nid:
            return [f"  {entry_nid} -> {child_entry};"]
        return []

    return [
        line
        for child, child_entry in zip(children, child_entries)
        for line in _edge_for_child(child, child_entry)
    ]


def build_dot(root: MethodSemanticCFG) -> str:
    lines = [
        "digraph ftrace {",
        "  rankdir=TB;",
        "  compound=true;",
        '  node [shape=box, style="filled,rounded", fillcolor=white, '
        'fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
        "",
    ]
    cross_edges: list[str] = []
    cluster_counter = [0]

    def next_cluster_id() -> str:
        cid = f"cluster_{cluster_counter[0]}"
        cluster_counter[0] += 1
        return cid

    def add_method(node: MethodSemanticCFG) -> str:
        """Add a method node. Returns entry node ID."""
        cls = short_class(node.get("class", "?"))
        method = node.get("method", "?")

        # Leaf nodes
        for leaf_kind in ("cycle", "ref", "filtered"):
            if node.get(leaf_kind):
                nid = f"n_leaf_{cluster_counter[0]}"
                cluster_counter[0] += 1
                label = f"{cls}.{method}\\n({leaf_kind})"
                style = NODE_STYLE[NodeKind(leaf_kind)]
                attrs = f'label="{escape(label)}"'
                for k, v in style.items():
                    attrs += f', {k}="{v}"'
                lines.append(f"  {nid} [{attrs}];")
                return nid

        nodes = node.get("nodes", [])
        edges = node.get("edges", [])
        clusters = node.get("clusters", [])
        exception_edges = node.get("exceptionEdges", [])
        children = node.get("children", [])
        line_start = node.get("lineStart", "?")
        line_end = node.get("lineEnd", "?")

        cid = next_cluster_id()
        lines.append(f"  subgraph {cid} {{")
        lines.append(
            f'    label="{escape(cls)}.{escape(method)} [{line_start}-{line_end}]";'
        )
        lines.append('    style="rounded,filled"; fillcolor="#f0f0f0";')
        lines.append('    color="#4a86c8";')
        lines.append("")

        # Nodes
        for n in nodes:
            lines.append(_render_node(n["id"], n))

        # Edges
        for e in edges:
            lines.append(_render_edge(e))

        # Trap clusters as nested subgraphs
        for i, cluster in enumerate(clusters):
            trap_type = cluster["trapType"]
            role = cluster["role"]
            node_ids = cluster.get("nodeIds", [])

            tc_id = f"cluster_trap_{i}"
            lines.append(f"    subgraph {tc_id} {{")

            if role == "try":
                lines.append(f'      label="try ({escape(trap_type)})";')
                lines.append(
                    '      style="dashed,rounded"; color="#ffa500"; fontcolor="#ffa500";'
                )
            else:
                h_label = (
                    "finally"
                    if trap_type.lower() in ("throwable", "any")
                    else f"catch ({escape(trap_type)})"
                )
                lines.append(f'      label="{h_label}";')
                lines.append(
                    '      style="dashed,rounded"; color="#007bff"; fontcolor="#007bff";'
                )

            for nid in node_ids:
                lines.append(f"      {nid};")
            lines.append("    }")

        # Exception edges
        for ee in exception_edges:
            lines.append(_render_exception_edge(ee, clusters))

        lines.append("  }")
        lines.append("")

        # Cross-cluster call edges to children
        # Build line → node ID lookup for call site matching
        line_to_nids: dict[int, list[str]] = {}
        for n in nodes:
            for ln in n.get("lines", []):
                line_to_nids.setdefault(ln, []).append(n["id"])

        entry_nid = node.get("entryNodeId", "") or (nodes[0]["id"] if nodes else "")

        for child in children:
            child_entry = add_method(child)
            if child_entry:
                csl = child.get("callSiteLine", -1)
                source_nids = line_to_nids.get(csl, [])
                if source_nids:
                    cross_edges.append(
                        f"  {source_nids[0]} -> {child_entry} "
                        f'[color="#e05050", style=bold, penwidth=1.5];'
                    )
                elif entry_nid:
                    cross_edges.append(f"  {entry_nid} -> {child_entry};")

        return entry_nid

    add_method(root)

    lines.append("  // Cross-cluster call edges")
    lines.extend(cross_edges)
    lines.append("}")
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Render semantic graph JSON as Graphviz DOT, then optionally produce SVG/PNG."
    )
    parser.add_argument(
        "--input", type=Path, help="Input semantic JSON file (default: stdin)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (.dot, .svg, or .png). Default: stdout as DOT.",
    )
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            root = json.load(f)
    else:
        root = json.load(sys.stdin)

    dot = build_dot(root)

    if args.output:
        ext = args.output.suffix.lower()
        if ext in (".svg", ".png"):
            import subprocess

            fmt = ext.lstrip(".")
            args.output.parent.mkdir(parents=True, exist_ok=True)
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
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(dot)
            print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(dot)


if __name__ == "__main__":
    main()
