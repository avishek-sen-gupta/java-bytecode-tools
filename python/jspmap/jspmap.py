"""jspmap CLI — trace JSP EL actions through a call graph to DAO methods."""

import argparse
import json
import re
import sys
from pathlib import Path

from jspmap.chain_builder import ChainHop, build_chains
from jspmap.jsf_bean_map import JsfBeanResolver
from jspmap.jsp_parser import ELAction, parse_jsps
from jspmap.protocols import BeanInfo, BeanResolver

# Registry of available resolver names → resolver classes.
# Add new resolvers here; no other file needs to change.
_RESOLVERS: dict[str, type[BeanResolver]] = {
    "jsf": JsfBeanResolver,
}


def _load_layer_patterns(path: Path | None) -> dict[str, re.Pattern]:
    if path is None:
        return {}
    return {name: re.compile(pat) for name, pat in json.loads(path.read_text()).items()}


def _hop_to_dict(hop: ChainHop) -> dict:
    return {
        "layer": hop.layer,
        "class": hop.fqcn,
        "method": hop.method,
        "signature": hop.signature,
    }


def _bean_to_dict(bean: BeanInfo | None) -> dict | None:
    if bean is None:
        return None
    return {"name": bean.name, "class": bean.fqcn, "scope": bean.scope}


def _entry_sigs_for(
    action: ELAction, call_graph: dict[str, list[str]], fqcn: str
) -> list[str]:
    prefix = f"<{fqcn}:"
    return [
        sig
        for sig in call_graph
        if sig.startswith(prefix) and f" {action.member}(" in sig
    ]


def _chains_for_action(
    action: ELAction,
    bean_map: dict[str, BeanInfo],
    call_graph: dict[str, list[str]],
    dao_pattern: re.Pattern,
    layer_patterns: dict[str, re.Pattern],
    max_depth: int,
) -> list[list[dict]]:
    bean = bean_map.get(action.bean_name)
    if bean is None or not action.member:
        return []
    return [
        [_hop_to_dict(h) for h in chain]
        for sig in _entry_sigs_for(action, call_graph, bean.fqcn)
        for chain in build_chains(
            call_graph, sig, dao_pattern, layer_patterns, max_depth
        )
    ]


def _action_to_dict(
    action: ELAction,
    bean_map: dict[str, BeanInfo],
    call_graph: dict[str, list[str]],
    dao_pattern: re.Pattern,
    layer_patterns: dict[str, re.Pattern],
    max_depth: int,
) -> dict:
    bean = bean_map.get(action.bean_name)
    entry_sigs = (
        _entry_sigs_for(action, call_graph, bean.fqcn) if bean and action.member else []
    )
    return {
        "jsp": action.jsp,
        "el": action.el,
        "el_context": {"tag": action.tag, "attribute": action.attribute},
        "bean": _bean_to_dict(bean),
        "entry_signature": entry_sigs[0] if entry_sigs else None,
        "chains": _chains_for_action(
            action, bean_map, call_graph, dao_pattern, layer_patterns, max_depth
        ),
    }


def run(
    jsps: Path,
    faces_config: Path,
    call_graph_path: Path,
    dao_pattern: str,
    resolver_name: str = "jsf",
    layers_path: Path | None = None,
    max_depth: int = 50,
    extensions: list[str] | None = None,
) -> dict:
    """Core pipeline. Returns the semantic map as a plain dict (JSON-serialisable)."""
    exts = extensions or ["jsp", "jspf", "xhtml"]
    dao_pat = re.compile(dao_pattern)
    layer_pats = _load_layer_patterns(layers_path)

    resolver_cls = _RESOLVERS.get(resolver_name)
    if resolver_cls is None:
        raise ValueError(
            f"Unknown resolver '{resolver_name}'. Known: {list(_RESOLVERS)}"
        )

    el_actions = parse_jsps(jsps, exts)
    bean_map = resolver_cls().resolve(faces_config)
    call_graph: dict[str, list[str]] = json.loads(call_graph_path.read_text())

    return {
        "meta": {
            "jsps_root": str(jsps),
            "faces_config": str(faces_config),
            "call_graph": str(call_graph_path),
            "dao_pattern": dao_pattern,
        },
        "actions": [
            _action_to_dict(
                action, bean_map, call_graph, dao_pat, layer_pats, max_depth
            )
            for action in el_actions
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trace JSP EL actions through a call graph to DAO methods."
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
        required=True,
        dest="dao_pattern",
        help="Regex matched against FQCN to identify DAO leaf nodes",
    )
    parser.add_argument(
        "--resolver",
        default="jsf",
        help=f"Bean resolver to use (default: jsf; available: {list(_RESOLVERS)})",
    )
    parser.add_argument(
        "--layers", type=Path, help="JSON file mapping layer name → FQCN regex"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=50,
        dest="max_depth",
        help="BFS depth cap (default: 50)",
    )
    parser.add_argument(
        "--extensions",
        default="jsp,jspf,xhtml",
        help="Comma-separated file extensions (default: jsp,jspf,xhtml)",
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
        layers_path=args.layers,
        max_depth=args.max_depth,
        extensions=exts,
    )

    out_json = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out_json)
        print(f"Wrote semantic map to {args.output}", file=sys.stderr)
    else:
        print(out_json)


if __name__ == "__main__":
    main()
