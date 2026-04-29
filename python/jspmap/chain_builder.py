"""BFS chain builder — finds all call chains from an entry point to DAO leaf nodes."""

import re
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ChainHop:
    signature: str  # full Soot method signature
    fqcn: str  # class name extracted from signature
    method: str  # method name extracted from signature
    layer: str  # caller-supplied layer label, or ""


def _fqcn_from_sig(sig: str) -> str:
    """'<com.example.Foo: void bar()>' → 'com.example.Foo'"""
    colon = sig.find(":")
    return sig[1:colon].strip() if colon != -1 else ""


def _method_from_sig(sig: str) -> str:
    """'<com.example.Foo: void bar()>' → 'bar'"""
    colon = sig.find(":")
    if colon == -1:
        return ""
    rest = sig[colon + 1 :].strip()
    parts = rest.split()
    if len(parts) < 2:
        return ""
    name_part = parts[1]
    paren = name_part.find("(")
    return name_part[:paren] if paren != -1 else name_part


def _assign_layer(fqcn: str, layer_patterns: dict[str, re.Pattern]) -> str:
    return next(
        (name for name, pat in layer_patterns.items() if pat.search(fqcn)),
        "",
    )


def _make_hop(sig: str, layer_patterns: dict[str, re.Pattern]) -> ChainHop:
    fqcn = _fqcn_from_sig(sig)
    return ChainHop(
        signature=sig,
        fqcn=fqcn,
        method=_method_from_sig(sig),
        layer=_assign_layer(fqcn, layer_patterns),
    )


def build_chains(
    call_graph: dict[str, list[str]],
    entry_signature: str,
    dao_pattern: re.Pattern,
    layer_patterns: dict[str, re.Pattern],
    max_depth: int = 50,
) -> list[list[ChainHop]]:
    """BFS from entry_signature. Returns all paths that terminate at a DAO node.

    A node is a DAO leaf when its FQCN matches dao_pattern.
    Cycles are detected by checking the current path; no chain is recorded.
    """
    initial = _make_hop(entry_signature, layer_patterns)
    queue: deque[tuple[str, tuple[ChainHop, ...]]] = deque(
        [(entry_signature, (initial,))]
    )
    chains: list[list[ChainHop]] = []

    while queue:
        sig, path = queue.popleft()
        if dao_pattern.search(_fqcn_from_sig(sig)):
            chains.append(list(path))
            continue
        if len(path) >= max_depth:
            continue
        path_sigs = frozenset(h.signature for h in path)
        queue.extend(
            (callee, path + (_make_hop(callee, layer_patterns),))
            for callee in call_graph.get(sig, [])
            if callee not in path_sigs
        )

    return chains
