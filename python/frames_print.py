"""Pretty-print the JSON output of `frames` or `calltree` backward-trace — flat {nodes, calls, metadata} schema."""

import argparse
import json
import sys
from pathlib import Path

_INDENT = "  "
_BRANCH = "└─ "
_PIPE = "   "


def find_roots(node_sigs: set[str], calls: list[dict]) -> set[str]:
    """Nodes with no incoming normal (non-filtered, non-cycle) call edges."""
    has_incoming = {
        c["to"] for c in calls if not c.get("filtered") and not c.get("cycle")
    }
    return node_sigs - has_incoming


def _build_adjacency(calls: list[dict]) -> dict[str, list[tuple[str, int]]]:
    """caller → [(callee_sig, callsite_line)] for normal edges only."""
    normal = [c for c in calls if not c.get("filtered") and not c.get("cycle")]
    callers = dict.fromkeys(c["from"] for c in normal)
    return {
        caller: [
            (c["to"], c.get("callSiteLine", 0)) for c in normal if c["from"] == caller
        ]
        for caller in callers
    }


def _dfs_paths(
    sig: str,
    target: str,
    adj: dict[str, list[tuple[str, int]]],
    path: tuple[str, ...],
) -> list[list[str]]:
    if sig == target and len(path) > 1:
        return [list(path)]
    return [
        chain
        for callee, _ in adj.get(sig, [])
        if callee not in path
        for chain in _dfs_paths(callee, target, adj, path + (callee,))
    ]


def collect_paths(roots: set[str], target: str, calls: list[dict]) -> list[list[str]]:
    """DFS from each root to target; return list of sig-chains."""
    adj = _build_adjacency(calls)
    return [
        path
        for root in sorted(roots)
        for path in _dfs_paths(root, target, adj, (root,))
    ]


def format_frame(node: dict) -> str:
    cls = node.get("class", "?")
    method = node.get("method", "?")
    line_start = node.get("lineStart", "?")
    line_end = node.get("lineEnd", "?")
    line_count = node.get("sourceLineCount", "?")
    return f"{cls}.{method}  L{line_start}-{line_end}  ({line_count} lines)"


def _callsite_for(caller: str, callee: str, calls: list[dict]) -> int:
    return next(
        (
            c.get("callSiteLine", 0)
            for c in calls
            if c["from"] == caller and c["to"] == callee
        ),
        0,
    )


def format_path(
    path: list[str], nodes: dict[str, dict], calls: list[dict], index: int
) -> str:
    lines = [f"Chain {index + 1}:"]
    for i, sig in enumerate(path):
        node = nodes.get(sig, {"class": "?", "method": "?"})
        if i == 0:
            callsite_str = ""
        else:
            callsite = _callsite_for(path[i - 1], sig, calls)
            callsite_str = f"@L{callsite}  " if callsite > 0 else ""
        prefix = _INDENT + (_BRANCH if i > 0 else "")
        extra_indent = _INDENT + _PIPE * (i - 1) if i > 1 else ""
        lines.append(f"{extra_indent}{prefix}{callsite_str}{format_frame(node)}")
    lines.append("")
    return "\n".join(lines)


def format_frames(data: dict) -> str:
    metadata = data.get("metadata", {})
    to_class = metadata.get("toClass", "?")
    to_line = metadata.get("toLine", "?")
    nodes: dict[str, dict] = data.get("nodes", {})
    calls: list[dict] = data.get("calls", [])

    header_parts = [f"Target: {to_class}  (line {to_line})"]
    if "fromClass" in metadata:
        header_parts.append(
            f"From:   {metadata['fromClass']}  (line {metadata.get('fromLine', '?')})"
        )

    if not nodes:
        return "\n".join(header_parts) + "\nFound:  no paths\n"

    target_sig = next(
        (sig for sig, nd in nodes.items() if nd.get("class") == to_class),
        "",
    )

    if not target_sig:
        return "\n".join(header_parts) + "\nFound:  no paths\n"

    roots = find_roots(set(nodes.keys()), calls)
    paths = collect_paths(roots, target_sig, calls)

    if not paths:
        return "\n".join(header_parts) + "\nFound:  no paths\n"

    header_parts.append(f"Found:  {len(paths)} chain{'s' if len(paths) != 1 else ''}\n")
    chain_blocks = [format_path(p, nodes, calls, i) for i, p in enumerate(paths)]
    return "\n".join(header_parts) + "\n".join(chain_blocks)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pretty-print frames/calltree {nodes, calls, metadata} output."
    )
    parser.add_argument("--input", type=Path, help="JSON file (default: stdin)")
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    src = sys.stdin if args.input is None else args.input.open()
    data = json.load(src)
    result = format_frames(data)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
        print(f"Wrote frames summary to {args.output}", file=sys.stderr)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
