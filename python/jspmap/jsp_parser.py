"""Parse JSP/XHTML files and extract EL expressions with source context."""

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup, Tag
from bs4.element import NavigableString

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ELAction:
    jsp: str  # relative path from jsps_root
    el: str  # raw expression text, e.g. "#{orderAction.submit}"
    tag: str  # enclosing tag name, or "_text" for text nodes
    attribute: str  # attribute name, or "_text" for text node content
    bean_name: str  # first identifier in the expression
    member: str  # first member access, or "" if none


def tokenize_el(text: str) -> list[str]:
    """Extract all #{...} and ${...} EL expressions from a string.

    Character-level scanner: tracks brace depth, skips braces inside
    single- and double-quoted string literals.
    """
    results = []
    i = 0
    n = len(text)
    while i < n - 1:
        if text[i] in ("#", "$") and text[i + 1] == "{":
            depth = 1
            start = i
            i += 2
            in_single = False
            in_double = False
            while i < n and depth > 0:
                ch = text[i]
                if in_single:
                    if ch == "'":
                        in_single = False
                elif in_double:
                    if ch == '"':
                        in_double = False
                else:
                    if ch == "'":
                        in_single = True
                    elif ch == '"':
                        in_double = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                i += 1
            if depth == 0:
                results.append(text[start:i])
        else:
            i += 1
    return results


_IDENT_RE = re.compile(r"^[a-zA-Z_]\w*")


def classify_el(expr: str) -> tuple[str, str]:
    """Parse #{beanName.member} → (bean_name, member).

    Returns ("", "") for expressions that do not start with a simple identifier.
    Returns (bean_name, "") when there is no member access.
    """
    inner = expr[2:-1].strip()
    m = _IDENT_RE.match(inner)
    if not m:
        return ("", "")
    bean = m.group(0)
    rest = inner[len(bean) :]
    if not rest.startswith("."):
        return (bean, "")
    after_dot = rest[1:]
    mem_m = _IDENT_RE.match(after_dot)
    return (bean, mem_m.group(0) if mem_m else "")


def _actions_from_value(jsp: str, tag: str, attr: str, value: str) -> list[ELAction]:
    return [
        ELAction(jsp=jsp, el=expr, tag=tag, attribute=attr, bean_name=bn, member=mem)
        for expr in tokenize_el(value)
        for bn, mem in [classify_el(expr)]
        if bn
    ]


def parse_jsps(jsps_root: Path, extensions: list[str]) -> list[ELAction]:
    """Walk jsps_root recursively for files matching extensions. Return all ELActions."""
    paths = sorted(
        path for ext in extensions for path in jsps_root.rglob(f"*.{ext.lstrip('.')}")
    )
    log.info(
        "Scanning %d files in %s (extensions: %s)", len(paths), jsps_root, extensions
    )
    actions = [action for path in paths for action in _parse_file(jsps_root, path)]
    log.info("Extracted %d EL actions from %d files", len(actions), len(paths))
    return actions


def _parse_file(root: Path, path: Path) -> list[ELAction]:
    rel = str(path.relative_to(root))
    log.debug("Parsing %s", rel)
    try:
        soup = BeautifulSoup(
            path.read_text(encoding="utf-8", errors="replace"), "html.parser"
        )
        return [
            action for tag in soup.find_all(True) for action in _parse_tag(rel, tag)
        ]
    except Exception as exc:
        print(f"Warning: could not parse {path}: {exc}", file=sys.stderr)
        return []


def _parse_tag(jsp: str, tag: Tag) -> list[ELAction]:
    tag_name = tag.name or "_text"
    attr_actions = [
        action
        for attr, val in (tag.attrs or {}).items()
        for action in _actions_from_value(
            jsp, tag_name, attr, " ".join(val) if isinstance(val, list) else str(val)
        )
    ]
    text_actions = [
        action
        for child in tag.children
        if isinstance(child, NavigableString)
        for action in _actions_from_value(jsp, tag_name, "_text", str(child))
    ]
    return attr_actions + text_actions
