"""jspmap CLI — trace JSP EL actions through a call graph; emits flat {nodes, calls, metadata}."""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from fw_calltree import build_graph as _calltree_build_graph
from node_types import NodeType
from jspmap.jsf_bean_map import JsfBeanResolver
from jspmap.jsp_parser import ELAction, parse_jsps
from jspmap.protocols import BeanInfo, BeanResolver

log = logging.getLogger(__name__)

_INCLUDE_RE = [
    re.compile(
        r'<jsp:include\s+[^>]*?page=["\']([^"\']+)["\']', re.IGNORECASE | re.DOTALL
    ),
    re.compile(r'<c:import\s+[^>]*?url=["\']([^"\']+)["\']', re.IGNORECASE | re.DOTALL),
    re.compile(
        r'<ui:include\s+[^>]*?src=["\']([^"\']+)["\']', re.IGNORECASE | re.DOTALL
    ),
    re.compile(r"<%@\s*include\s+file=[\"']([^\"']+)[\"']", re.IGNORECASE),
]


def _extract_include_paths(content: str) -> list[str]:
    return [
        m.group(1)
        for pat in _INCLUDE_RE
        for m in pat.finditer(content)
        if "${" not in m.group(1) and "#{" not in m.group(1)
    ]


def _resolve_includes(jsps_root: Path, jsp_rel: str, raw_paths: list[str]) -> list[str]:
    base = (jsps_root / jsp_rel).parent
    resolved = []
    for raw in raw_paths:
        if raw.startswith("http://") or raw.startswith("https://"):
            continue
        candidate = (
            (jsps_root / raw.lstrip("/")).resolve()
            if raw.startswith("/")
            else (base / raw).resolve()
        )
        try:
            rel = str(candidate.relative_to(jsps_root.resolve()))
            if (jsps_root / rel).exists():
                resolved.append(rel)
        except ValueError:
            pass
    return resolved


def _collect_jsp_includes(
    jsps_root: Path, jsp_set: frozenset[str]
) -> dict[str, list[str]]:
    return {
        jsp: [
            rel
            for rel in _resolve_includes(
                jsps_root,
                jsp,
                _extract_include_paths(
                    (jsps_root / jsp).read_text(encoding="utf-8", errors="replace")
                ),
            )
            if rel in jsp_set
        ]
        for jsp in jsp_set
    }


def _collect_jsp_set(jsps_root: Path, start: str) -> frozenset[str]:
    visited: set[str] = {start}
    queue = [start]
    while queue:
        current = queue.pop()
        path = jsps_root / current
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        for rel in _resolve_includes(
            jsps_root, current, _extract_include_paths(content)
        ):
            if rel not in visited:
                visited.add(rel)
                queue.append(rel)
    return frozenset(visited)


_RESOLVERS: dict[str, type[BeanResolver]] = {
    "jsf": JsfBeanResolver,
}

_DEFAULT_EXTENSIONS: list[str] = ["jsp", "jspf", "xhtml"]


def _entry_sigs_for(
    action: ELAction, call_graph: dict[str, list[str]], fqcn: str
) -> list[str]:
    prefix = f"<{fqcn}:"
    return [
        sig
        for sig in call_graph
        if sig.startswith(prefix) and f" {action.member}(" in sig
    ]


def _jsp_node_key(jsp: str) -> str:
    return f"jsp:/{jsp}"


def _el_node_key(jsp: str, el: str) -> str:
    return f"el:/{jsp}#{el}"


def _make_jsp_node(jsp: str) -> dict:
    key = _jsp_node_key(jsp)
    return {
        "node_type": NodeType.JSP,
        "class": f"/{jsp}",
        "method": "",
        "methodSignature": key,
    }


def _make_el_node(jsp: str, el: str) -> dict:
    key = _el_node_key(jsp, el)
    return {
        "node_type": NodeType.EL_EXPRESSION,
        "class": f"/{jsp}",
        "method": el,
        "methodSignature": key,
        "expression": el,
    }


def _graft_action(
    action: ELAction,
    bean_map: dict[str, BeanInfo],
    call_graph: dict[str, list[str]],
    callsites: dict[str, dict[str, int]],
    method_lines: dict[str, dict],
    pat: re.Pattern,
    nodes: dict[str, dict],
    calls: list[dict],
    visited: set[str],
) -> None:
    bean = bean_map.get(action.bean_name)

    jsp_key = _jsp_node_key(action.jsp)
    nodes[jsp_key] = _make_jsp_node(action.jsp)

    if bean is None or not action.member:
        return

    if action.el:
        el_key = _el_node_key(action.jsp, action.el)
        nodes[el_key] = _make_el_node(action.jsp, action.el)
        calls.append(
            {"from": jsp_key, "to": el_key, "edge_info": {"edge_type": "el_call"}}
        )
        source_key = el_key
    else:
        source_key = jsp_key

    for sig in _entry_sigs_for(action, call_graph, bean.fqcn):
        calls.append(
            {"from": source_key, "to": sig, "edge_info": {"edge_type": "method_call"}}
        )
        _calltree_build_graph(
            sig,
            call_graph,
            pat,
            set(),
            visited,
            nodes,
            calls,
            callsites,
            method_lines,
            "",
        )


def run(
    jsps: Path,
    faces_config: Path,
    call_graph_path: Path,
    dao_pattern: str = ".",
    resolver_name: str = "jsf",
    pattern: str = ".",
    extensions: list[str] = _DEFAULT_EXTENSIONS,
    jsp_filter: str = "",
    recurse: bool = False,
) -> dict:
    """Core pipeline. Returns flat {nodes, calls, metadata} graph."""
    exts = list(extensions)
    pat = re.compile(pattern)

    resolver_cls = _RESOLVERS.get(resolver_name)
    if resolver_cls is None:
        raise ValueError(
            f"Unknown resolver '{resolver_name}'. Known: {list(_RESOLVERS)}"
        )

    log.info("jspmap starting: jsps=%s extensions=%s", jsps, exts)
    el_actions = parse_jsps(jsps, exts)
    log.info("parse_jsps: %d EL actions", len(el_actions))

    jsp_set: frozenset[str] = frozenset()
    if jsp_filter:
        if recurse:
            jsp_set = _collect_jsp_set(jsps, jsp_filter)
            log.info(
                "jsp_filter=%s recurse=True: JSP set has %d files",
                jsp_filter,
                len(jsp_set),
            )
            el_actions = [a for a in el_actions if a.jsp in jsp_set]
        else:
            el_actions = [a for a in el_actions if a.jsp == jsp_filter]
        log.info("After filter: %d EL actions", len(el_actions))

    log.info(
        "Resolving beans from %s using %s resolver...", faces_config, resolver_name
    )
    bean_map = resolver_cls().resolve(faces_config)
    log.info("Bean map: %d beans resolved", len(bean_map))

    log.info("Loading call graph from %s...", call_graph_path)
    cg_data: dict = json.loads(call_graph_path.read_text())
    call_graph: dict[str, list[str]] = cg_data.get("callees", cg_data)
    callsites: dict[str, dict[str, int]] = cg_data.get("callsites", {})
    method_lines: dict[str, dict] = cg_data.get("methodLines", {})
    log.info("Call graph loaded: %d callers", len(call_graph))

    metadata: dict = {
        "tool": "jspmap",
        "jsps_root": str(jsps),
        "faces_config": str(faces_config),
        "call_graph": str(call_graph_path),
        "dao_pattern": dao_pattern,
    }
    if jsp_filter:
        metadata["jsp_filter"] = jsp_filter
    if recurse and jsp_set:
        metadata["jsp_set"] = sorted(jsp_set)
        metadata["jsp_includes"] = {
            k: v for k, v in _collect_jsp_includes(jsps, jsp_set).items()
        }

    nodes: dict[str, dict] = {}
    calls: list[dict] = []
    visited: set[str] = set()

    log.info("Grafting %d EL actions...", len(el_actions))
    for action in el_actions:
        _graft_action(
            action,
            bean_map,
            call_graph,
            callsites,
            method_lines,
            pat,
            nodes,
            calls,
            visited,
        )
    log.info("Done: %d nodes, %d edges", len(nodes), len(calls))

    return {"nodes": nodes, "calls": calls, "metadata": metadata}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(
        description="Trace JSP EL actions through a call graph; emits flat {nodes, calls, metadata}."
    )
    parser.add_argument(
        "--jsps", required=True, type=Path, help="Root directory of JSP files"
    )
    parser.add_argument(
        "--faces-config",
        required=True,
        type=Path,
        dest="faces_config",
        help="Path to the resolver config file (e.g. faces-config.xml)",
    )
    parser.add_argument(
        "--call-graph",
        required=True,
        type=Path,
        dest="call_graph",
        help="Call graph JSON from buildcg",
    )
    parser.add_argument(
        "--dao-pattern",
        default=".",
        dest="dao_pattern",
        help="Stored in metadata for reference (default: .)",
    )
    parser.add_argument(
        "--pattern",
        default=".",
        help="Regex matched against FQCN to scope the Java call graph (default: . = all)",
    )
    parser.add_argument(
        "--resolver",
        default="jsf",
        help=f"Bean resolver to use (default: jsf; available: {list(_RESOLVERS)})",
    )
    parser.add_argument(
        "--layers", type=Path, help="Accepted for backward compatibility (unused)"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=50,
        dest="max_depth",
        help="Accepted for backward compatibility (unused)",
    )
    parser.add_argument(
        "--extensions",
        default="jsp,jspf,xhtml",
        help="Comma-separated file extensions (default: jsp,jspf,xhtml)",
    )
    parser.add_argument(
        "--jsp",
        dest="jsp_filter",
        default="",
        help="Restrict analysis to a single JSP (relative path from --jsps root)",
    )
    parser.add_argument(
        "--recurse",
        action="store_true",
        default=False,
        help="Also include JSPs transitively included by --jsp",
    )
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    exts = [e.strip() for e in args.extensions.split(",")]
    result = run(
        jsps=args.jsps,
        faces_config=args.faces_config,
        call_graph_path=args.call_graph,
        dao_pattern=args.dao_pattern,
        resolver_name=args.resolver,
        pattern=args.pattern,
        extensions=exts,
        jsp_filter=args.jsp_filter,
        recurse=args.recurse,
    )

    out_json = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out_json)
        print(f"Wrote jspmap flat graph to {args.output}", file=sys.stderr)
    else:
        print(out_json)


if __name__ == "__main__":
    main()
