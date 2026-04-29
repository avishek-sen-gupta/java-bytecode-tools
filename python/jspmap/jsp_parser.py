"""Parse JSP/XHTML files and extract EL expressions with source context."""

from dataclasses import dataclass
from pathlib import Path


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
