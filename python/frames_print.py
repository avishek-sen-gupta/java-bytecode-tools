"""Pretty-print the JSON output of the `frames` backward-trace command."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_INDENT = "  "
_BRANCH = "└─ "
_PIPE = "   "


def _flatten_chain(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Walk the singly-linked children list and return frames in call order."""
    children = node.get("children", [])
    return [node] + (_flatten_chain(children[0]) if children else [])


def _format_frame(frame: dict[str, Any]) -> str:
    cls = frame.get("class", "?")
    method = frame.get("method", "?")
    line_start = frame.get("lineStart", "?")
    line_end = frame.get("lineEnd", "?")
    line_count = frame.get("sourceLineCount", "?")
    return f"{cls}.{method}  L{line_start}-{line_end}  ({line_count} lines)"


def _format_chain(index: int, chain_root: dict[str, Any]) -> str:
    frames = _flatten_chain(chain_root)
    lines = [f"Chain {index + 1}:"]
    for i, frame in enumerate(frames):
        callsite = frame.get("callSiteLine", 0)
        callsite_str = f"@L{callsite}  " if (i > 0 and callsite > 0) else ""
        prefix = _INDENT + (_BRANCH if i > 0 else "")
        extra_indent = _INDENT + _PIPE * (i - 1) if i > 1 else ""
        lines.append(f"{extra_indent}{prefix}{callsite_str}{_format_frame(frame)}")
    lines.append("")
    return "\n".join(lines)


def _format_frames(data: dict[str, Any]) -> str:
    to_class = data.get("toClass", "?")
    to_line = data.get("toLine", "?")
    found = data.get("found", False)

    header_parts = [f"Target: {to_class}  (line {to_line})"]
    if "fromClass" in data:
        header_parts.append(
            f"From:   {data['fromClass']}  (line {data.get('fromLine', '?')})"
        )

    if not found:
        return "\n".join(header_parts) + "\nFound:  no paths\n"

    trace = data.get("trace", {})
    chains = trace.get("children", [])
    header_parts.append(
        f"Found:  {len(chains)} chain{'s' if len(chains) != 1 else ''}\n"
    )
    chain_blocks = [_format_chain(i, chain) for i, chain in enumerate(chains)]
    return "\n".join(header_parts) + "\n".join(chain_blocks)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pretty-print the JSON output of the frames backward-trace command."
    )
    parser.add_argument("--input", type=Path, help="Frames JSON file (default: stdin)")
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    src = sys.stdin if args.input is None else args.input.open()
    data = json.load(src)
    result = _format_frames(data)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result)
        print(f"Wrote frames summary to {args.output}", file=sys.stderr)
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
