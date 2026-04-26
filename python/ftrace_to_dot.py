#!/usr/bin/env python3
"""Convert forward-trace JSON tree to Graphviz DOT, then optionally render SVG/PNG."""

import json
import sys
from pathlib import Path


def short_class(fqcn: str) -> str:
    """Extract short class name from fully qualified name."""
    return fqcn.rsplit(".", 1)[-1]


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def merge_source_trace(source_trace: list[dict]) -> list[dict]:
    """Deduplicate sourceTrace by line number, merging calls and branches."""
    by_line: dict[int, dict] = {}
    for entry in source_trace:
        line = entry["line"]
        if line < 0:
            continue
        if line not in by_line:
            by_line[line] = {"line": line, "calls": set(), "branches": []}
        for c in entry.get("calls", []):
            by_line[line]["calls"].add(c)
        if "branch" in entry:
            by_line[line]["branches"].append(entry["branch"])
    return [by_line[ln] for ln in sorted(by_line)]


def merge_block_stmts(stmts: list[dict]) -> list[dict]:
    """Deduplicate block stmts by line number, merging calls and branches."""
    by_line: dict[int, dict] = {}
    for s in stmts:
        line = s["line"]
        if line < 0:
            continue
        if line not in by_line:
            by_line[line] = {"line": line, "calls": [], "branches": [], "assigns": []}
        if "call" in s:
            by_line[line]["calls"].append(s["call"])
        if "branch" in s:
            by_line[line]["branches"].append(s["branch"])
        if "assign" in s:
            by_line[line]["assigns"].append(s["assign"])
    return [by_line[ln] for ln in sorted(by_line)]


def build_dot(root: dict) -> str:
    lines = [
        "digraph ftrace {",
        "  rankdir=TB;",
        "  compound=true;",
        '  node [shape=box, style="filled,rounded", fillcolor=white, '
        'fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
        "",
    ]
    cluster_id = [0]
    node_id = [0]
    # cross-cluster edges added after all clusters are defined
    cross_edges: list[str] = []

    def next_node():
        nid = f"n{node_id[0]}"
        node_id[0] += 1
        return nid

    def next_cluster():
        cid = f"cluster_{cluster_id[0]}"
        cluster_id[0] += 1
        return cid

    def make_line_label(entry: dict) -> str:
        """Build a label for a source line entry (merged stmts)."""
        parts = [f"L{entry['line']}"]
        for c in sorted(entry.get("calls", [])):
            parts.append(
                short_class(c.rsplit(".", 1)[0]) + "." + c.rsplit(".", 1)[-1]
                if "." in c
                else c
            )
        # Show constant assignments when no calls are present (e.g. ternary false branch)
        if not entry.get("calls"):
            for a in entry.get("assigns", []):
                parts.append(a)
        return r"\n".join(escape(p) for p in parts)

    def line_fill(entry: dict) -> str:
        """Color for a source line node."""
        if entry.get("branches"):
            return "#cce5ff"
        elif entry.get("calls"):
            return "#d4edda"
        elif entry.get("assigns"):
            return "#f5f5dc"
        return "white"

    def add_method(node: dict) -> str | None:
        """Add a method as a cluster. Returns entry node ID."""
        cls = short_class(node.get("class", node.get("fromClass", "?")))
        method = node.get("method", "?")

        # Leaf nodes: ref, cycle, filtered — single box, no cluster
        if node.get("cycle"):
            nid = next_node()
            label = f"{cls}.{method}\\n(cycle)"
            lines.append(
                f'  {nid} [label="{escape(label)}", fillcolor="#ffcccc", '
                f'style="filled,rounded,dashed", color="red"];'
            )
            return nid
        if node.get("ref"):
            nid = next_node()
            label = f"{cls}.{method}\\n(ref)"
            lines.append(
                f'  {nid} [label="{escape(label)}", fillcolor="#e8e8e8", '
                f'style="filled,rounded,dashed", color="#999999"];'
            )
            return nid
        if node.get("filtered"):
            nid = next_node()
            label = f"{cls}.{method}\\n(filtered)"
            lines.append(
                f'  {nid} [label="{escape(label)}", fillcolor="#fff3cd", '
                f'style="filled,rounded,dashed", color="#cc9900"];'
            )
            return nid

        blocks = node.get("blocks", [])
        traps = node.get("traps", [])
        children = node.get("children", [])
        line_start = node.get("lineStart", "?")
        line_end = node.get("lineEnd", "?")

        # Build a map: callSiteLine -> list of children at that line
        callsite_children: dict[int, list[dict]] = {}
        for child in children:
            csl = child.get("callSiteLine", -1)
            callsite_children.setdefault(csl, []).append(child)

        cid = next_cluster()
        lines.append(f"  subgraph {cid} {{")
        lines.append(
            f'    label="{escape(cls)}.{escape(method)} [{line_start}-{line_end}]";'
        )
        lines.append('    style="rounded,filled"; fillcolor="#f0f0f0";')
        lines.append(f'    color="#4a86c8";')
        lines.append("")

        # ---- Block-level CFG rendering (per-line nodes) ----
        if blocks:
            # Per-block: first line node ID and last line node ID
            block_first: dict[str, str] = {}
            block_last: dict[str, str] = {}
            # Map blockId -> list of node IDs for trap clustering
            bid_to_nids: dict[str, list[str]] = {}
            # Map source line -> node ID (for cross-cluster call edges)
            line_to_nids: dict[int, list[str]] = {}
            entry_nid = None

            for block in blocks:
                bid = block["id"]
                merged = merge_block_stmts(block.get("stmts", []))

                if not merged:
                    # Empty block — single placeholder node
                    nid = next_node()
                    lines.append(f'    {nid} [label="{bid}", fillcolor="white"];')
                    block_first[bid] = nid
                    block_last[bid] = nid
                    bid_to_nids.setdefault(bid, []).append(nid)
                    if entry_nid is None:
                        entry_nid = nid
                    continue

                # Emit one node per source line, connected sequentially
                prev_nid = None
                is_branch_block = bool(block.get("branchCondition"))
                for idx, entry in enumerate(merged):
                    nid = next_node()
                    bid_to_nids.setdefault(bid, []).append(nid)
                    label = make_line_label(entry)
                    fill = line_fill(entry)
                    # Last node in a branch block gets diamond shape
                    is_last = idx == len(merged) - 1
                    if is_branch_block and is_last:
                        cond = block.get("branchCondition", "")
                        if cond:
                            label += r"\n" + escape(cond)
                        lines.append(
                            f'    {nid} [label="{label}", fillcolor="{fill}", '
                            f"shape=diamond];"
                        )
                    else:
                        lines.append(
                            f'    {nid} [label="{label}", fillcolor="{fill}"];'
                        )

                    line_to_nids.setdefault(entry["line"], []).append(nid)

                    if bid not in block_first:
                        block_first[bid] = nid
                    if entry_nid is None:
                        entry_nid = nid
                    if prev_nid is not None:
                        lines.append(f"    {prev_nid} -> {nid};")
                    prev_nid = nid

                block_last[bid] = prev_nid

            # CFG edges between blocks: last node of block -> first node of successor
            for block in blocks:
                bid = block["id"]
                tail_nid = block_last.get(bid)
                if not tail_nid:
                    continue
                successors = block.get("successors", [])
                branch_cond = block.get("branchCondition")
                if len(successors) == 2 and branch_cond:
                    true_nid = block_first.get(successors[0])
                    false_nid = block_first.get(successors[1])
                    if true_nid:
                        lines.append(
                            f"    {tail_nid} -> {true_nid} "
                            f'[label="T", color="#28a745", fontcolor="#28a745"];'
                        )
                    if false_nid:
                        lines.append(
                            f"    {tail_nid} -> {false_nid} "
                            f'[label="F", color="#dc3545", fontcolor="#dc3545"];'
                        )
                else:
                    for succ_id in successors:
                        succ_nid = block_first.get(succ_id)
                        if succ_nid:
                            lines.append(f"    {tail_nid} -> {succ_nid};")

            # ---- Traps (Exception Handlers) as nested clusters ----
            for i, trap in enumerate(traps):
                etype = short_class(trap["type"])

                # 1. Try/Covered region (Orange)
                t_cid = f"{cid}_try_{i}"
                lines.append(f"    subgraph {t_cid} {{")
                lines.append(f'      label="try ({escape(etype)})";')
                lines.append(
                    '      style="dashed,rounded"; color="#ffa500"; fontcolor="#ffa500";'
                )
                for bid in trap.get("coveredBlocks", []):
                    for nid in bid_to_nids.get(bid, []):
                        lines.append(f"      {nid};")
                lines.append("    }")

                # 2. Handler region (Blue)
                h_cid = f"{cid}_handler_{i}"
                h_label = (
                    "finally"
                    if etype.lower() in ("throwable", "any")
                    else f"catch ({escape(etype)})"
                )
                lines.append(f"    subgraph {h_cid} {{")
                lines.append(f'      label="{escape(h_label)}";')
                lines.append(
                    '      style="dashed,rounded"; color="#007bff"; fontcolor="#007bff";'
                )
                for bid in trap.get("handlerBlocks", []):
                    for nid in bid_to_nids.get(bid, []):
                        lines.append(f"      {nid};")
                lines.append("    }")

                # Edge from try-cluster to handler-entry.
                handler_bid = trap["handler"]
                handler_nid = block_first.get(handler_bid)
                covered_bids = trap.get("coveredBlocks", [])
                if handler_nid and covered_bids:
                    last_bid = covered_bids[-1]
                    last_nid = block_last.get(last_bid)
                    if last_nid:
                        lines.append(
                            f"    {last_nid} -> {handler_nid} "
                            f'[label="{escape(etype)}", color="#ffa500", style="dashed", '
                            f'fontcolor="#ffa500", ltail="{t_cid}", lhead="{h_cid}"];'
                        )

            lines.append("  }")
            lines.append("")

            # Process children — draw cross-cluster edges from call site line
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

        # ---- Fallback: linear sourceTrace rendering (no blocks) ----
        source_trace = node.get("sourceTrace", [])
        merged = merge_source_trace(source_trace)

        if not merged:
            nid = next_node()
            lines.append(
                f'    {nid} [label="{escape(cls)}.{escape(method)}", fillcolor="#d4edda"];'
            )
            lines.append("  }")
            lines.append("")
            for child in children:
                child_entry = add_method(child)
                if child_entry:
                    cross_edges.append(f"  {nid} -> {child_entry};")
            return nid

        line_node_ids: dict[int, str] = {}
        entry_nid = None
        for entry in merged:
            ln = entry["line"]
            nid = next_node()
            line_node_ids[ln] = nid
            if entry_nid is None:
                entry_nid = nid
            label = make_line_label(entry)
            fill = line_fill(entry)
            lines.append(f'    {nid} [label="{label}", fillcolor="{fill}"];')

        prev_nid = None
        for entry in merged:
            nid = line_node_ids[entry["line"]]
            if prev_nid is not None:
                lines.append(f"    {prev_nid} -> {nid};")
            prev_nid = nid

        lines.append("  }")
        lines.append("")

        for child in children:
            child_entry = add_method(child)
            if child_entry:
                csl = child.get("callSiteLine", -1)
                source_nid = line_node_ids.get(csl)
                if source_nid:
                    cross_edges.append(
                        f"  {source_nid} -> {child_entry} "
                        f'[color="#e05050", style=bold, penwidth=1.5];'
                    )
                else:
                    cross_edges.append(f"  {prev_nid} -> {child_entry};")

        return entry_nid

    add_method(root)

    lines.append("  // Cross-cluster call edges")
    lines.extend(cross_edges)
    lines.append("}")
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert forward-trace JSON tree to Graphviz DOT, then optionally render SVG/PNG."
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="Input forward-trace JSON file"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (.dot, .svg, or .png). If .svg/.png, runs Graphviz dot to render. Default: stdout as DOT.",
    )
    args = parser.parse_args()

    with open(args.input) as f:
        root = json.load(f)

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
