"""Render a calltree as an ASCII tree.

Pipeline:
  calltree ... | calltree-print
  calltree-print --input tree.json
"""

from ftrace_types import MethodCFG, short_class


def _line_suffix(node: MethodCFG) -> str:
    line_start = node.get("lineStart", "")
    line_end = node.get("lineEnd", "")
    if not line_start:
        return ""
    if line_start == line_end:
        return f":{line_start}"
    return f":{line_start}-{line_end}"


def _format_label(node: MethodCFG) -> str:
    base = (
        short_class(node.get("class", "?"))
        + "."
        + node.get("method", "?")
        + _line_suffix(node)
    )
    if node.get("ref"):
        return base + " [ref]"
    if node.get("cycle"):
        return base + " [↻]"
    return base


def _render_subtree(node: MethodCFG, prefix: str, is_last: bool) -> list[str]:
    connector = "└── " if is_last else "├── "
    own = [prefix + connector + _format_label(node)]
    if node.get("ref") or node.get("cycle"):
        return own
    children = node.get("children", [])
    child_prefix = prefix + ("    " if is_last else "│   ")
    return [
        *own,
        *(
            line
            for i, child in enumerate(children)
            for line in _render_subtree(child, child_prefix, i == len(children) - 1)
        ),
    ]


def render_tree(trace: MethodCFG) -> list[str]:
    root_line = [_format_label(trace)]
    if trace.get("ref") or trace.get("cycle"):
        return root_line
    children = trace.get("children", [])
    return [
        *root_line,
        *(
            line
            for i, child in enumerate(children)
            for line in _render_subtree(child, "", i == len(children) - 1)
        ),
    ]


def main() -> None:
    import argparse
    import json
    import sys
    from pathlib import Path
    from typing import cast

    parser = argparse.ArgumentParser(description="Render a calltree as an ASCII tree.")
    parser.add_argument("--input", type=Path, help="Input JSON (default: stdin)")
    args = parser.parse_args()

    data = (
        json.loads(Path(args.input).read_text()) if args.input else json.load(sys.stdin)
    )

    trace = cast(MethodCFG, data.get("trace", data))
    for line in render_tree(trace):
        print(line)


if __name__ == "__main__":
    main()
