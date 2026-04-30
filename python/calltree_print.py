"""Render a calltree or frames flat {nodes, calls} output as an ASCII tree.

Pipeline:
  calltree ... | calltree-print
  frames  ...  | calltree-print
  calltree-print --input tree.json
"""

from ftrace_types import short_class


def _make_label(node: dict, callsite_line: int = 0) -> str:
    base = short_class(node.get("class", "?")) + "." + node.get("method", "?")
    if callsite_line > 0:
        base = base + f":{callsite_line}"
    return base


def _build_adjacency(
    calls: list[dict],
) -> dict[str, list[tuple[str, int, bool]]]:
    """caller → [(callee_sig, callsite_line, is_cycle)]."""
    adj: dict[str, list[tuple[str, int, bool]]] = {}
    for c in calls:
        if c.get("filtered"):
            continue
        caller = c["from"]
        callee = c["to"]
        callsite = c.get("callSiteLine", 0)
        is_cycle = bool(c.get("cycle"))
        adj.setdefault(caller, []).append((callee, callsite, is_cycle))
    return adj


def _find_roots(node_sigs: set[str], calls: list[dict]) -> list[str]:
    has_incoming = {
        c["to"] for c in calls if not c.get("filtered") and not c.get("cycle")
    }
    return sorted(node_sigs - has_incoming)


def _render_subtree(
    sig: str,
    adj: dict[str, list[tuple[str, int, bool]]],
    nodes: dict[str, dict],
    prefix: str,
    is_last: bool,
    visited: set[str],
    callsite_line: int,
    is_cycle: bool,
) -> list[str]:
    connector = "└── " if is_last else "├── "
    node = nodes.get(sig, {"class": "?", "method": "?"})
    label = _make_label(node, callsite_line)
    if is_cycle:
        label = label + " [↻]"
    own_line = prefix + connector + label
    if is_cycle or sig in visited:
        return [own_line]

    visited = visited | {sig}
    children = adj.get(sig, [])
    child_prefix = prefix + ("    " if is_last else "│   ")
    child_lines = [
        line
        for i, (child_sig, child_callsite, child_cycle) in enumerate(children)
        for line in _render_subtree(
            child_sig,
            adj,
            nodes,
            child_prefix,
            i == len(children) - 1,
            visited,
            child_callsite,
            child_cycle,
        )
    ]
    return [own_line, *child_lines]


def render_flat(nodes: dict[str, dict], calls: list[dict]) -> list[str]:
    adj = _build_adjacency(calls)
    roots = _find_roots(set(nodes.keys()), calls)
    result: list[str] = []
    for root_sig in roots:
        node = nodes.get(root_sig, {"class": "?", "method": "?"})
        result.append(_make_label(node))
        children = adj.get(root_sig, [])
        visited = {root_sig}
        for i, (child_sig, child_callsite, child_cycle) in enumerate(children):
            result.extend(
                _render_subtree(
                    child_sig,
                    adj,
                    nodes,
                    "",
                    i == len(children) - 1,
                    visited,
                    child_callsite,
                    child_cycle,
                )
            )
    return result


def main() -> None:
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Render a calltree/frames flat graph as an ASCII tree."
    )
    parser.add_argument("--input", type=Path, help="Input JSON (default: stdin)")
    args = parser.parse_args()

    data = (
        json.loads(Path(args.input).read_text()) if args.input else json.load(sys.stdin)
    )

    nodes: dict[str, dict] = data.get("nodes", {})
    calls: list[dict] = data.get("calls", [])
    for line in render_flat(nodes, calls):
        print(line)


if __name__ == "__main__":
    main()
