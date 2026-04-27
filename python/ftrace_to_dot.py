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
from typing import TypedDict, cast

from ftrace_types import (
    ExceptionEdge,
    MethodSemanticCFG,
    NodeKind,
    BranchLabel,
    SplineStyle,
    SemanticCluster,
    SemanticEdge,
    SemanticNode,
    short_class,
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


def _render_exception_edge(
    ee: ExceptionEdge, clusters: list[SemanticCluster], method_counter: int
) -> str:
    """Render an exception edge with ltail/lhead cluster references."""
    src, dst = ee["from"], ee["to"]
    trap_type = escape(ee["trapType"])
    attrs = (
        f'label="{trap_type}", color="#ffa500", style="dashed", ' f'fontcolor="#ffa500"'
    )
    from_idx = ee.get("fromCluster", -1)
    to_idx = ee.get("toCluster", -1)
    if from_idx >= 0 and clusters[from_idx].get("nodeIds", []):
        attrs += f', ltail="cluster_trap_{method_counter}_{from_idx}"'
    if to_idx >= 0 and clusters[to_idx].get("nodeIds", []):
        attrs += f', lhead="cluster_trap_{method_counter}_{to_idx}"'
    return f"    {src} -> {dst} [{attrs}];"


class _MethodDotResult(TypedDict):
    lines: list[str]
    cross_edges: list[str]
    next_counter: int
    entry_nid: str


class _FoldChildAcc(TypedDict):
    results: list[_MethodDotResult]
    counter: int


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


def _render_trap_cluster(
    index: int, cluster: SemanticCluster, method_counter: int
) -> list[str]:
    """Render one trap cluster as a DOT subgraph."""
    trap_type = cluster["trapType"]
    role = cluster["role"]
    node_ids = cluster.get("nodeIds", [])

    tc_id = f"cluster_trap_{method_counter}_{index}"
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


def _render_method(node: MethodSemanticCFG, counter: int) -> _MethodDotResult:
    """Recursively render a method and its children as DOT lines."""
    # Leaf check
    leaf_kind = next(
        (k for k in ("cycle", "ref", "filtered") if node.get(k, False)),
        "",
    )
    if leaf_kind:
        leaf_lines, nid, next_counter = _render_leaf(node, counter)
        return {
            "lines": leaf_lines,
            "cross_edges": [],
            "next_counter": next_counter,
            "entry_nid": nid,
        }

    # Extract fields
    cls = short_class(node.get("class", "?"))
    method_name = node.get("method", "?")
    nodes = node.get("nodes", [])
    edges = node.get("edges", [])
    clusters = node.get("clusters", [])
    exception_edges = node.get("exceptionEdges", [])
    children = node.get("children", [])
    line_start = node.get("lineStart", "?")
    line_end = node.get("lineEnd", "?")
    entry_nid = node.get("entryNodeId", "") or (nodes[0]["id"] if nodes else "")

    # Subgraph for this method
    cid = f"cluster_{counter}"
    subgraph = [
        f"  subgraph {cid} {{",
        f'    label="{escape(cls)}.{escape(method_name)} [{line_start}-{line_end}]";',
        '    style="rounded,filled"; fillcolor="#f0f0f0";',
        '    color="#4a86c8";',
        "",
        *[_render_node(n["id"], n) for n in nodes],
        *[_render_edge(e) for e in edges],
        *[
            line
            for i, c in enumerate(clusters)
            for line in _render_trap_cluster(i, c, counter)
        ],
        *[_render_exception_edge(ee, clusters, counter) for ee in exception_edges],
        "  }",
        "",
    ]

    # Recurse children, threading counter
    def _fold_child(
        acc: _FoldChildAcc,
        child: MethodSemanticCFG,
    ) -> _FoldChildAcc:
        result = _render_method(child, acc["counter"])
        return _FoldChildAcc(
            results=[*acc["results"], result],
            counter=result["next_counter"],
        )

    folded: _FoldChildAcc = reduce(
        _fold_child,
        children,
        _FoldChildAcc(results=[], counter=counter + 1),
    )

    child_results: list[_MethodDotResult] = folded["results"]
    child_lines = [line for r in child_results for line in r["lines"]]
    child_cross = [edge for r in child_results for edge in r["cross_edges"]]
    child_entries = [r["entry_nid"] for r in child_results]

    cross_edges = [
        *child_cross,
        *_render_cross_edges(nodes, children, child_entries, entry_nid),
    ]

    return _MethodDotResult(
        lines=[*subgraph, *child_lines],
        cross_edges=cross_edges,
        next_counter=folded["counter"],
        entry_nid=entry_nid,
    )


def build_dot(root: MethodSemanticCFG, splines: str = "") -> str:
    """Render a MethodSemanticCFG tree as a Graphviz DOT string."""
    header = [
        "digraph ftrace {",
        "  rankdir=TB;",
        "  compound=true;",
        *([f'  splines="{splines}";'] if splines else []),
        '  node [shape=box, style="filled,rounded", fillcolor=white, '
        'fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
        "",
    ]
    result = _render_method(root, 0)
    footer = ["  // Cross-cluster call edges", *result["cross_edges"], "}"]
    return "\n".join([*header, *result["lines"], *footer])


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
    parser.add_argument(
        "--splines",
        type=SplineStyle,
        choices=list(SplineStyle),
        default=None,
        help="Edge routing style (default: Graphviz default, i.e. spline).",
    )
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            root = json.load(f)
    else:
        root = json.load(sys.stdin)

    dot = build_dot(root, splines=args.splines or "")

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
