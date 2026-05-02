"""Format a backward-slice DDG as ASCII or Graphviz DOT/SVG.

Pipeline:
  bwd-slice ... | ddg-format --ascii
  bwd-slice ... | ddg-format --dot [-o out.svg]
  ddg-format --ascii --input slice.json
"""

import re

from ftrace_types import short_class

# --- Types ---

NodeId = tuple[str, str]  # (method, stmtId)
Edge = tuple[NodeId, NodeId, str]  # (from, to, edge_kind)


# --- Parsing ---


def _node_id(node: dict) -> NodeId:
    return (node["method"], node["stmtId"])


def _edge_id(endpoint: dict) -> NodeId:
    return (endpoint["method"], endpoint["stmtId"])


def _short_method(method_sig: str) -> str:
    """Extract ClassName.methodName from a full Soot signature."""
    match = re.search(r"<([^:]+):\s+\S+\s+(\w+)\(", method_sig)
    if not match:
        return method_sig
    fqcn, method = match.group(1), match.group(2)
    return short_class(fqcn) + "." + method


def parse_slice(data: dict) -> tuple[dict[NodeId, dict], list[Edge], list[NodeId]]:
    """Parse bwd-slice JSON into indexed nodes, edges, and root node IDs."""
    nodes_by_id = {_node_id(n): n for n in data.get("nodes", [])}
    edges = [
        (_edge_id(e["from"]), _edge_id(e["to"]), e["edge_info"]["kind"])
        for e in data.get("edges", [])
    ]
    has_incoming = frozenset(e[1] for e in edges)
    roots = [nid for nid in nodes_by_id if nid not in has_incoming]
    return nodes_by_id, edges, roots


# --- ASCII rendering ---


def _node_label(node: dict) -> str:
    method = _short_method(node["method"])
    line = node.get("line", 0)
    stmt = node.get("stmt", "")
    return f"[{method} L{line}] {stmt}"


def _build_children(
    edges: list[Edge],
) -> dict[NodeId, list[tuple[NodeId, str]]]:
    """Build parent → [(child, edge_kind)] adjacency."""
    children: dict[NodeId, list[tuple[NodeId, str]]] = {}
    for src, dst, kind in edges:
        children.setdefault(src, []).append((dst, kind))
    return children


def _render_ascii_subtree(
    nid: NodeId,
    nodes_by_id: dict[NodeId, dict],
    children: dict[NodeId, list[tuple[NodeId, str]]],
    prefix: str,
    is_last: bool,
    visited: frozenset[NodeId],
    edge_kind: str,
) -> list[str]:
    connector = "└── " if is_last else "├── "
    node = nodes_by_id.get(nid, {"method": "?", "stmtId": "?", "stmt": "?"})
    kind_tag = f"--{edge_kind}--> " if edge_kind else ""
    label = kind_tag + _node_label(node)
    own_line = prefix + connector + label

    if nid in visited:
        return [own_line + " [↻]"]

    next_visited = visited | {nid}
    kids = children.get(nid, [])
    child_prefix = prefix + ("    " if is_last else "│   ")
    child_lines = [
        line
        for i, (child_nid, ek) in enumerate(kids)
        for line in _render_ascii_subtree(
            child_nid,
            nodes_by_id,
            children,
            child_prefix,
            i == len(kids) - 1,
            next_visited,
            ek,
        )
    ]
    return [own_line, *child_lines]


def render_ascii(
    nodes_by_id: dict[NodeId, dict],
    edges: list[Edge],
    roots: list[NodeId],
) -> list[str]:
    """Render the slice as an ASCII tree rooted at origin nodes."""
    children = _build_children(edges)
    lines: list[str] = []
    for root in roots:
        node = nodes_by_id.get(root, {"method": "?", "stmtId": "?", "stmt": "?"})
        lines.append(_node_label(node))
        kids = children.get(root, [])
        for i, (child_nid, ek) in enumerate(kids):
            lines.extend(
                _render_ascii_subtree(
                    child_nid,
                    nodes_by_id,
                    children,
                    "",
                    i == len(kids) - 1,
                    frozenset({root}),
                    ek,
                )
            )
    return lines


# --- DOT rendering ---

EDGE_COLORS = {
    "LOCAL": "black",
    "PARAM": "blue",
    "RETURN": "forestgreen",
}


def _sanitize_id(nid: NodeId) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", f"{nid[0]}_{nid[1]}")


def _dot_label(node: dict) -> str:
    method = _short_method(node["method"])
    line = node.get("line", 0)
    stmt = node.get("stmt", "").replace('"', '\\"')
    return f"{method}\\nL{line}: {stmt}"


def _node_shape(node: dict) -> str:
    kind = node.get("kind", "")
    if kind == "IDENTITY":
        return "invhouse"
    if kind == "RETURN":
        return "house"
    if kind in ("INVOKE", "ASSIGN_INVOKE"):
        return "box3d"
    return "box"


def render_dot(
    nodes_by_id: dict[NodeId, dict],
    edges: list[Edge],
) -> str:
    """Render the slice as a Graphviz DOT digraph."""
    # Group nodes by method for subgraph clusters
    methods: dict[str, list[NodeId]] = {}
    for nid, node in nodes_by_id.items():
        methods.setdefault(node["method"], []).append(nid)

    parts = [
        "digraph bwd_slice {",
        "  rankdir=TB;",
        '  node [fontname="Courier" fontsize=10];',
    ]

    for i, (method_sig, nids) in enumerate(methods.items()):
        label = _short_method(method_sig).replace('"', '\\"')
        parts.append(f"  subgraph cluster_{i} {{")
        parts.append(f'    label="{label}";')
        parts.append("    style=dashed;")
        for nid in nids:
            node = nodes_by_id[nid]
            sid = _sanitize_id(nid)
            lbl = _dot_label(node)
            shape = _node_shape(node)
            parts.append(f'    {sid} [label="{lbl}" shape={shape}];')
        parts.append("  }")

    for src, dst, kind in edges:
        color = EDGE_COLORS.get(kind, "gray")
        parts.append(
            f'  {_sanitize_id(src)} -> {_sanitize_id(dst)} [label="{kind}" color={color} fontcolor={color}];'
        )

    parts.append("}")
    return "\n".join(parts) + "\n"


# --- CLI ---


def main() -> None:
    import argparse
    import json
    import subprocess
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Format a backward-slice DDG as ASCII or DOT/SVG."
    )
    parser.add_argument("--input", type=Path, help="Input JSON (default: stdin)")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output file (default: stdout)"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--ascii", action="store_true", help="Pretty-printed ASCII tree")
    mode.add_argument("--dot", action="store_true", help="Graphviz DOT (raw)")
    mode.add_argument("--svg", action="store_true", help="Render to SVG via dot")
    args = parser.parse_args()

    data = (
        json.loads(Path(args.input).read_text()) if args.input else json.load(sys.stdin)
    )
    nodes_by_id, edges, roots = parse_slice(data)

    if args.ascii:
        output = "\n".join(render_ascii(nodes_by_id, edges, roots)) + "\n"
        if args.output:
            args.output.write_text(output)
        else:
            print(output, end="")
        return

    dot = render_dot(nodes_by_id, edges)

    if args.dot:
        if args.output:
            args.output.write_text(dot)
        else:
            print(dot, end="")
        return

    # --svg
    result = subprocess.run(
        ["dot", "-Tsvg"],
        input=dot,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    if args.output:
        args.output.write_text(result.stdout)
    else:
        print(result.stdout, end="")


if __name__ == "__main__":
    main()
