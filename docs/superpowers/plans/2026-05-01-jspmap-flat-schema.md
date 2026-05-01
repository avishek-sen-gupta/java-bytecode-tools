# jspmap Flat Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace jspmap's legacy `{meta, actions}` output with the shared flat `{nodes, calls, metadata}` schema; add mandatory `node_type`/`edge_info` fields to all producers; delete `jspmap_to_dot.py`.

**Architecture:** calltree.py and frames.py gain `node_type: "java_method"` on nodes and `edge_info: {}` on edges (breaking schema change). jspmap rewrites its `run()` to graft JSP/EL prefix nodes onto a calltree-built Java subgraph, emitting a single flat document. `jspmap_to_dot.py` is deleted; users pipe `jspmap | calltree-to-dot` instead.

**Tech Stack:** Python 3.13, pytest, existing `calltree.build_graph()` library function (no subprocess).

---

## File Map

| File | Action |
|---|---|
| `python/calltree.py` | Add `node_type: "java_method"` to `_node_entry()`; add `edge_info: {}` to all three edge emission sites in `build_graph()` |
| `python/frames.py` | Add `node_type: "java_method"` to `_node_entry()`; add `edge_info: {}` to edge in `build_frames_graph()` |
| `python/jspmap/jspmap.py` | Full rewrite: remove chain_builder/dao-pattern logic, add calltree graft, emit flat schema |
| `python/jspmap_to_dot.py` | **Delete** |
| `python/tests/test_calltree.py` | Add assertions: `node_type == "java_method"` and `edge_info == {}` on every node/edge |
| `python/tests/test_frames.py` | Same additions |
| `python/jspmap/tests/test_jspmap.py` | Full rewrite for flat schema assertions |
| `python/tests/test_calltree_to_dot.py` | Add three new producer-scenario tests (calltree, frames, jspmap) |
| `python/tests/test_jspmap_to_dot.py` | **Delete** |
| `python/pyproject.toml` | Remove `jspmap-to-dot` entry |
| `README.md` | Update Tool Combinations diagram; remove `jspmap-to-dot` from tool list |

---

## Task 1: calltree — add `node_type` and `edge_info`

**Files:**
- Modify: `python/calltree.py`
- Test: `python/tests/test_calltree.py`

### Background

`calltree._node_entry()` builds the dict stored in `nodes[sig]`. `build_graph()` emits call edges at three sites:
1. Line ~67: cycle edge `{"from": caller_sig, "to": sig, "cycle": True}`
2. Line ~77: filtered edge `{"from": caller_sig, "to": sig, "filtered": True}`
3. Line ~86: normal edge `{"from": caller_sig, "to": sig}`

All three need `"edge_info": {}`. All nodes need `"node_type": "java_method"`.

- [ ] **Step 1: Add two failing tests to `python/tests/test_calltree.py`**

Add inside `class TestBuildGraph` — append after the last existing test method:

```python
    def test_node_has_node_type_java_method(self):
        from calltree import build_graph

        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            METHOD_LINES,
            "",
        )
        assert nodes[SIG_A]["node_type"] == "java_method"

    def test_normal_edge_has_edge_info(self):
        from calltree import build_graph

        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_B]), (SIG_B, [])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            METHOD_LINES,
            "",
        )
        edge = next(c for c in calls if c["from"] == SIG_A and c["to"] == SIG_B)
        assert edge["edge_info"] == {}

    def test_cycle_edge_has_edge_info(self):
        from calltree import build_graph

        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_B]), (SIG_B, [SIG_A])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            METHOD_LINES,
            "",
        )
        cycle_edge = next(c for c in calls if c.get("cycle"))
        assert cycle_edge["edge_info"] == {}

    def test_filtered_edge_has_edge_info(self):
        from calltree import build_graph

        SIG_OTHER = "<other.pkg.X: void run()>"
        nodes, calls = {}, []
        build_graph(
            SIG_A,
            _cg([(SIG_A, [SIG_OTHER])]),
            _pat("com.example"),
            set(),
            set(),
            nodes,
            calls,
            {},
            {},
            "",
        )
        filtered_edge = next(c for c in calls if c.get("filtered"))
        assert filtered_edge["edge_info"] == {}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd python && uv run pytest tests/test_calltree.py::TestBuildGraph::test_node_has_node_type_java_method tests/test_calltree.py::TestBuildGraph::test_normal_edge_has_edge_info tests/test_calltree.py::TestBuildGraph::test_cycle_edge_has_edge_info tests/test_calltree.py::TestBuildGraph::test_filtered_edge_has_edge_info -v
```

Expected: 4 failures — `KeyError: 'node_type'` and `KeyError: 'edge_info'`.

- [ ] **Step 3: Edit `python/calltree.py`**

In `_node_entry()`, change:
```python
    base: dict[str, str | int] = {
        "class": cls,
        "method": method,
        "methodSignature": sig,
    }
```
to:
```python
    base: dict[str, str | int] = {
        "node_type": "java_method",
        "class": cls,
        "method": method,
        "methodSignature": sig,
    }
```

In `build_graph()`, there are three edge emission sites. Change each one:

**Site 1 — cycle edge** (in the `if sig in on_path:` block):
```python
        edge: dict = {"from": caller_sig, "to": sig, "cycle": True, "edge_info": {}}
```

**Site 2 — filtered edge** (in the `if not in_scope:` block):
```python
            edge = {"from": caller_sig, "to": sig, "filtered": True, "edge_info": {}}
```

**Site 3 — normal edge** (in the `# Emit caller→sig edge` block):
```python
        edge = {"from": caller_sig, "to": sig, "edge_info": {}}
```

- [ ] **Step 4: Run the new tests to confirm they pass**

```bash
cd python && uv run pytest tests/test_calltree.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd python && git add calltree.py tests/test_calltree.py
git commit -m "feat: add node_type and edge_info to calltree schema"
```

---

## Task 2: frames — add `node_type` and `edge_info`

**Files:**
- Modify: `python/frames.py`
- Test: `python/tests/test_frames.py`

### Background

`frames._node_entry()` builds node dicts. `build_frames_graph()` emits edges at one site (line ~159):
```python
edge: dict = {"from": caller, "to": callee}
```

- [ ] **Step 1: Add failing tests to `python/tests/test_frames.py`**

Add inside `class TestBuildFramesGraph`:

```python
    def test_node_has_node_type_java_method(self):
        from frames import build_frames_graph

        nodes, calls = build_frames_graph(
            [[SIG_MAIN, SIG_SVC, SIG_DAO]], CALLSITES, METHOD_LINES
        )
        assert nodes[SIG_MAIN]["node_type"] == "java_method"
        assert nodes[SIG_DAO]["node_type"] == "java_method"

    def test_edge_has_edge_info(self):
        from frames import build_frames_graph

        nodes, calls = build_frames_graph(
            [[SIG_MAIN, SIG_SVC, SIG_DAO]], CALLSITES, METHOD_LINES
        )
        for edge in calls:
            assert edge["edge_info"] == {}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd python && uv run pytest tests/test_frames.py::TestBuildFramesGraph::test_node_has_node_type_java_method tests/test_frames.py::TestBuildFramesGraph::test_edge_has_edge_info -v
```

Expected: 2 failures.

- [ ] **Step 3: Edit `python/frames.py`**

In `_node_entry()`, change:
```python
    base: dict = {"class": cls, "method": method, "methodSignature": sig}
```
to:
```python
    base: dict = {"node_type": "java_method", "class": cls, "method": method, "methodSignature": sig}
```

In `build_frames_graph()`, change:
```python
                edge: dict = {"from": caller, "to": callee}
```
to:
```python
                edge: dict = {"from": caller, "to": callee, "edge_info": {}}
```

- [ ] **Step 4: Run full frames tests**

```bash
cd python && uv run pytest tests/test_frames.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd python && git add frames.py tests/test_frames.py
git commit -m "feat: add node_type and edge_info to frames schema"
```

---

## Task 3: Rewrite jspmap to emit flat schema

**Files:**
- Modify: `python/jspmap/jspmap.py`
- Test: `python/jspmap/tests/test_jspmap.py`

### Background

The existing `run()` returns `{"meta": ..., "actions": [...]}`. The new `run()` returns `{"nodes": {}, "calls": [], "metadata": {}}`.

**New `run()` internal flow:**

```
For each EL action:
  1. Emit jsp node  (key: "jsp:/" + action.jsp)
  2. If action.el non-empty:
       - Emit el_expression node  (key: "el:/" + action.jsp + "#" + action.el)
       - Emit JSP→EL edge with edge_info: {edge_type: "el_call"}
  3. For each entry_sig in call_graph matching bean.fqcn + action.member:
       - Emit EL→entry_sig (or JSP→entry_sig if no EL) edge with edge_info: {edge_type: "method_call"}
       - Call calltree.build_graph(entry_sig, ...) with shared visited set
```

**Key implementation details:**
- `visited: set[str] = set()` is shared across all `_graft_action()` calls → Java nodes deduplicated globally
- `on_path: set[str] = set()` is fresh per `build_graph()` call (cycle detection is per-DFS)
- `build_graph()` is called with `caller_sig=""` → no edge emitted from "" to entry_sig (jspmap emits that edge with its own `edge_info`)
- jspmap loads both `callsites` and `methodLines` from buildcg JSON (currently only loads `callees`)
- `--dao-pattern` is kept in CLI and stored in metadata (backward compat); it no longer controls graph filtering
- `--pattern` is the new calltree-level filter (default `"."` = all classes in scope)
- `--layers` and `--max-depth` remain accepted by CLI but are no longer used internally

**Node key formats:**
- JSP node key: `"jsp:/order.jsp"` (note: leading `jsp:/` + relative path)
- EL node key: `"el:/order.jsp##{orderAction.submit}"` (note: EL `#{...}` syntax means double `#` after the fragment separator)

**Node dict formats:**

JSP node (key `"jsp:/order.jsp"`):
```json
{
  "node_type": "jsp",
  "class": "/order.jsp",
  "method": "",
  "methodSignature": "jsp:/order.jsp"
}
```

EL node (key `"el:/order.jsp##{orderAction.submit}"`):
```json
{
  "node_type": "el_expression",
  "class": "/order.jsp",
  "method": "#{orderAction.submit}",
  "methodSignature": "el:/order.jsp##{orderAction.submit}",
  "expression": "#{orderAction.submit}"
}
```

**The test fixture `CALL_GRAPH` format:** The existing test file has CALL_GRAPH as a raw dict (no `callees` wrapper). The new jspmap.py reads `cg_data.get("callees", cg_data)`, so the raw dict still works.

**What is `action.el` vs `action.member`?** From `jspmap.jsp_parser.ELAction`:
- `action.el` = the full EL expression string e.g. `"#{orderAction.submit}"`
- `action.bean_name` = `"orderAction"`
- `action.member` = `"submit"` (the method name portion)
- `action.jsp` = `"order.jsp"` (relative path from jsps root)

- [ ] **Step 1: Write failing tests in `python/jspmap/tests/test_jspmap.py`**

Replace the entire file content with:

```python
"""Integration tests for jspmap CLI — flat {nodes, calls, metadata} schema."""

import json
import textwrap

import pytest

from jspmap.jspmap import run

FACES_CONFIG = textwrap.dedent("""\
    <?xml version="1.0"?>
    <faces-config>
      <managed-bean>
        <managed-bean-name>orderAction</managed-bean-name>
        <managed-bean-class>com.example.web.OrderAction</managed-bean-class>
        <managed-bean-scope>session</managed-bean-scope>
      </managed-bean>
    </faces-config>
""")

# Raw callees dict — jspmap reads cg_data.get("callees", cg_data) so this works
CALL_GRAPH = {
    "<com.example.web.OrderAction: void submit()>": [
        "<com.example.svc.OrderService: void place()>"
    ],
    "<com.example.svc.OrderService: void place()>": [
        "<com.example.dao.JdbcDao: void save()>"
    ],
    "<com.example.dao.JdbcDao: void save()>": [],
}

JSP_KEY = "jsp:/order.jsp"
EL_KEY = "el:/order.jsp##{orderAction.submit}"
ENTRY_SIG = "<com.example.web.OrderAction: void submit()>"
SVC_SIG = "<com.example.svc.OrderService: void place()>"
DAO_SIG = "<com.example.dao.JdbcDao: void save()>"


@pytest.fixture()
def workspace(tmp_path):
    jsp_dir = tmp_path / "jsps"
    jsp_dir.mkdir()
    (jsp_dir / "order.jsp").write_text(
        '<h:commandButton action="#{orderAction.submit}" />'
    )
    faces = tmp_path / "faces-config.xml"
    faces.write_text(FACES_CONFIG)
    cg = tmp_path / "callgraph.json"
    cg.write_text(json.dumps(CALL_GRAPH))
    return {"jsp_dir": jsp_dir, "faces": faces, "cg": cg, "tmp": tmp_path}


@pytest.fixture()
def result(workspace):
    return run(
        jsps=workspace["jsp_dir"],
        faces_config=workspace["faces"],
        call_graph_path=workspace["cg"],
    )


class TestFlatSchemaStructure:
    def test_output_has_nodes_calls_metadata(self, result):
        assert "nodes" in result
        assert "calls" in result
        assert "metadata" in result

    def test_no_legacy_meta_or_actions_keys(self, result):
        assert "meta" not in result
        assert "actions" not in result

    def test_metadata_tool_is_jspmap(self, result):
        assert result["metadata"]["tool"] == "jspmap"

    def test_metadata_has_required_keys(self, workspace, result):
        meta = result["metadata"]
        assert "jsps_root" in meta
        assert "faces_config" in meta
        assert "call_graph" in meta

    def test_output_is_json_serialisable(self, result):
        serialised = json.dumps(result)
        assert json.loads(serialised) == result


class TestJspNode:
    def test_jsp_node_present(self, result):
        assert JSP_KEY in result["nodes"]

    def test_jsp_node_type(self, result):
        assert result["nodes"][JSP_KEY]["node_type"] == "jsp"

    def test_jsp_node_method_signature(self, result):
        assert result["nodes"][JSP_KEY]["methodSignature"] == JSP_KEY

    def test_jsp_node_method_is_empty(self, result):
        assert result["nodes"][JSP_KEY]["method"] == ""


class TestElNode:
    def test_el_node_present(self, result):
        assert EL_KEY in result["nodes"]

    def test_el_node_type(self, result):
        assert result["nodes"][EL_KEY]["node_type"] == "el_expression"

    def test_el_node_has_expression_field(self, result):
        assert result["nodes"][EL_KEY]["expression"] == "#{orderAction.submit}"

    def test_el_node_method_signature(self, result):
        assert result["nodes"][EL_KEY]["methodSignature"] == EL_KEY


class TestJavaNodes:
    def test_entry_sig_node_present(self, result):
        assert ENTRY_SIG in result["nodes"]

    def test_entry_sig_node_type_java_method(self, result):
        assert result["nodes"][ENTRY_SIG]["node_type"] == "java_method"

    def test_dao_node_present(self, result):
        assert DAO_SIG in result["nodes"]

    def test_all_java_nodes_have_node_type(self, result):
        java_sigs = [ENTRY_SIG, SVC_SIG, DAO_SIG]
        for sig in java_sigs:
            assert result["nodes"][sig]["node_type"] == "java_method"


class TestCallEdges:
    def _edge(self, result, from_key, to_key):
        return next(
            (c for c in result["calls"] if c["from"] == from_key and c["to"] == to_key),
            None,
        )

    def test_jsp_to_el_edge_present(self, result):
        assert self._edge(result, JSP_KEY, EL_KEY) is not None

    def test_jsp_to_el_edge_type(self, result):
        edge = self._edge(result, JSP_KEY, EL_KEY)
        assert edge["edge_info"] == {"edge_type": "el_call"}

    def test_el_to_entry_edge_present(self, result):
        assert self._edge(result, EL_KEY, ENTRY_SIG) is not None

    def test_el_to_entry_edge_type(self, result):
        edge = self._edge(result, EL_KEY, ENTRY_SIG)
        assert edge["edge_info"] == {"edge_type": "method_call"}

    def test_java_java_edges_have_empty_edge_info(self, result):
        java_edges = [
            c
            for c in result["calls"]
            if c["from"] not in (JSP_KEY, EL_KEY) and c["to"] not in (JSP_KEY, EL_KEY)
            and not c.get("filtered")
            and not c.get("cycle")
        ]
        assert java_edges, "expected at least one Java→Java edge"
        for edge in java_edges:
            assert edge["edge_info"] == {}

    def test_all_edges_have_edge_info_key(self, result):
        for edge in result["calls"]:
            assert "edge_info" in edge, f"missing edge_info on: {edge}"


class TestNewCallgraphFormat:
    def test_callees_subkey_format_works(self, workspace, tmp_path):
        cg = tmp_path / "cg_new.json"
        cg.write_text(json.dumps({"callees": CALL_GRAPH, "callsites": {}, "methodLines": {}}))
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=cg,
        )
        assert ENTRY_SIG in result["nodes"]
        assert DAO_SIG in result["nodes"]


class TestUnresolvedBean:
    def test_unresolved_bean_produces_only_jsp_node(self, workspace, tmp_path):
        jsp_dir = tmp_path / "j2"
        jsp_dir.mkdir()
        (jsp_dir / "page.jsp").write_text(
            '<h:commandButton action="#{unknownBean.go}" />'
        )
        result = run(
            jsps=jsp_dir,
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
        )
        # Should have a JSP node for the page but no EL or Java nodes
        assert "jsp:/page.jsp" in result["nodes"]
        assert not any(k.startswith("el:") for k in result["nodes"])
        assert not any(k.startswith("<") for k in result["nodes"])


class TestPatternFiltering:
    def test_pattern_filters_out_of_scope_nodes(self, workspace):
        # Only include web layer — svc and dao should be filtered edges, not nodes
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            pattern=r"com\.example\.web",
        )
        assert ENTRY_SIG in result["nodes"]
        assert SVC_SIG not in result["nodes"]
        assert DAO_SIG not in result["nodes"]
```

- [ ] **Step 2: Run to confirm all new tests fail**

```bash
cd python && uv run pytest jspmap/tests/test_jspmap.py -v 2>&1 | head -50
```

Expected: errors importing `run` with the new signature, or assertion failures on schema structure.

- [ ] **Step 3: Rewrite `python/jspmap/jspmap.py`**

Replace the entire file with:

```python
"""jspmap CLI — trace JSP EL actions through a call graph; emits flat {nodes, calls, metadata}."""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

from calltree import build_graph as _calltree_build_graph
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
        "node_type": "jsp",
        "class": f"/{jsp}",
        "method": "",
        "methodSignature": key,
    }


def _make_el_node(jsp: str, el: str) -> dict:
    key = _el_node_key(jsp, el)
    return {
        "node_type": "el_expression",
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
        calls.append({"from": jsp_key, "to": el_key, "edge_info": {"edge_type": "el_call"}})
        source_key = el_key
    else:
        source_key = jsp_key

    for sig in _entry_sigs_for(action, call_graph, bean.fqcn):
        calls.append({"from": source_key, "to": sig, "edge_info": {"edge_type": "method_call"}})
        _calltree_build_graph(sig, call_graph, pat, set(), visited, nodes, calls, callsites, method_lines, "")


def run(
    jsps: Path,
    faces_config: Path,
    call_graph_path: Path,
    dao_pattern: str = ".",
    resolver_name: str = "jsf",
    pattern: str = ".",
    extensions: list[str] | None = None,
    jsp_filter: str = "",
    recurse: bool = False,
) -> dict:
    """Core pipeline. Returns flat {nodes, calls, metadata} graph."""
    exts = extensions or ["jsp", "jspf", "xhtml"]
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
        _graft_action(action, bean_map, call_graph, callsites, method_lines, pat, nodes, calls, visited)
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
```

- [ ] **Step 4: Run the new tests**

```bash
cd python && uv run pytest jspmap/tests/test_jspmap.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run entire test suite to check for regressions**

```bash
cd python && uv run pytest -v
```

Expected: all tests pass (old chain_builder and other jspmap unit tests that reference removed functions may now be dead — check if any are left).

- [ ] **Step 6: Commit**

```bash
cd python && git add jspmap/jspmap.py jspmap/tests/test_jspmap.py
git commit -m "feat: rewrite jspmap to emit flat {nodes, calls, metadata} schema"
```

---

## Task 4: calltree-to-dot — add producer-scenario tests

**Files:**
- Test: `python/tests/test_calltree_to_dot.py`

### Background

The spec requires tests covering DOT generation for all three producer use cases: calltree output, frames output, and jspmap output. `calltree_to_dot.py` rendering logic needs no changes — the existing `render_dot()`, `collect_nodes_flat()`, `collect_edges_flat()` already handle arbitrary node/edge dicts, ignoring unknown fields like `node_type` and `edge_info`.

The key functions to test end-to-end here are: `collect_nodes_flat()`, `collect_edges_flat()`, `find_roots()`, and `render_dot()` together — feeding them data shaped like real producer output.

- [ ] **Step 1: Add three producer-scenario test classes to `python/tests/test_calltree_to_dot.py`**

Append to the end of the existing file:

```python
# ---------------------------------------------------------------------------
# Producer-scenario tests — verify DOT rendering for all three input sources
# ---------------------------------------------------------------------------

SIG_ROOT = "<com.example.Root: void entry()>"
SIG_LEAF = "<com.example.Leaf: void work()>"


def _java_node(sig: str, cls: str, method: str) -> dict:
    return {"node_type": "java_method", "class": cls, "method": method, "methodSignature": sig}


def _jsp_node(jsp: str) -> dict:
    key = f"jsp:/{jsp}"
    return {"node_type": "jsp", "class": f"/{jsp}", "method": "", "methodSignature": key}


def _el_node(jsp: str, el: str) -> dict:
    key = f"el:/{jsp}#{el}"
    return {"node_type": "el_expression", "class": f"/{jsp}", "method": el, "methodSignature": key, "expression": el}


class TestDotFromCalltreeOutput:
    """calltree emits: nodes with node_type=java_method, calls with edge_info={}."""

    def _make_data(self):
        nodes = {
            SIG_ROOT: _java_node(SIG_ROOT, "com.example.Root", "entry"),
            SIG_LEAF: _java_node(SIG_LEAF, "com.example.Leaf", "work"),
        }
        calls = [
            {"from": SIG_ROOT, "to": SIG_LEAF, "edge_info": {}},
        ]
        return nodes, calls

    def test_both_nodes_in_dot(self):
        from calltree_to_dot import collect_nodes_flat, collect_edges_flat, find_roots, render_dot

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {sig: nd["class"].split(".")[-1] + "." + nd["method"] for sig, nd in nodes.items()}
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert "Root.entry" in dot
        assert "Leaf.work" in dot

    def test_edge_rendered_in_dot(self):
        from calltree_to_dot import collect_nodes_flat, collect_edges_flat, find_roots, render_dot

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {sig: nd["class"].split(".")[-1] + "." + nd["method"] for sig, nd in nodes.items()}
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert "->" in dot

    def test_edge_info_field_does_not_break_rendering(self):
        from calltree_to_dot import collect_edges_flat

        calls = [{"from": SIG_ROOT, "to": SIG_LEAF, "edge_info": {}}]
        edges, cycle_edges = collect_edges_flat(calls)
        assert (SIG_ROOT, SIG_LEAF) in edges


class TestDotFromFramesOutput:
    """frames emits: nodes with node_type=java_method, calls with edge_info={} (backward trace subset)."""

    def _make_data(self):
        # frames backward trace: main → svc → dao; only svc→dao path shown
        SIG_SVC = "<com.example.Svc: void handle()>"
        SIG_DAO = "<com.example.Dao: void save()>"
        nodes = {
            SIG_SVC: _java_node(SIG_SVC, "com.example.Svc", "handle"),
            SIG_DAO: _java_node(SIG_DAO, "com.example.Dao", "save"),
        }
        calls = [
            {"from": SIG_SVC, "to": SIG_DAO, "edge_info": {}, "callSiteLine": 35},
        ]
        return nodes, calls

    def test_both_nodes_rendered(self):
        from calltree_to_dot import collect_nodes_flat, collect_edges_flat, find_roots, render_dot

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {sig: nd["method"] for sig, nd in nodes.items()}
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert "handle" in dot
        assert "save" in dot

    def test_node_type_field_ignored_cleanly(self):
        from calltree_to_dot import collect_nodes_flat

        SIG_SVC = "<com.example.Svc: void handle()>"
        nodes = {SIG_SVC: _java_node(SIG_SVC, "com.example.Svc", "handle")}
        # Must not raise — unknown fields like node_type are ignored
        result = collect_nodes_flat(nodes)
        assert SIG_SVC in result


class TestDotFromJspmapOutput:
    """jspmap emits: JSP+EL+java_method nodes, edges with typed edge_info."""

    JSP_KEY = "jsp:/order.jsp"
    EL_KEY = "el:/order.jsp##{orderAction.submit}"
    ENTRY_SIG = "<com.example.web.OrderAction: void submit()>"
    DAO_SIG = "<com.example.dao.JdbcDao: void save()>"

    def _make_data(self):
        nodes = {
            self.JSP_KEY: _jsp_node("order.jsp"),
            self.EL_KEY: _el_node("order.jsp", "#{orderAction.submit}"),
            self.ENTRY_SIG: _java_node(self.ENTRY_SIG, "com.example.web.OrderAction", "submit"),
            self.DAO_SIG: _java_node(self.DAO_SIG, "com.example.dao.JdbcDao", "save"),
        }
        calls = [
            {"from": self.JSP_KEY, "to": self.EL_KEY, "edge_info": {"edge_type": "el_call"}},
            {"from": self.EL_KEY, "to": self.ENTRY_SIG, "edge_info": {"edge_type": "method_call"}},
            {"from": self.ENTRY_SIG, "to": self.DAO_SIG, "edge_info": {}},
        ]
        return nodes, calls

    def test_all_four_node_types_in_dot(self):
        from calltree_to_dot import collect_nodes_flat, collect_edges_flat, find_roots, render_dot, _make_dot_label

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {sig: _make_dot_label(nd) for sig, nd in nodes.items()}
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert self.JSP_KEY.replace(":", "_").replace("/", "_").replace(".", "_") in dot or "order" in dot
        # All 4 sigs must appear as sanitized IDs
        from calltree_to_dot import _sanitize_id
        for sig in [self.JSP_KEY, self.EL_KEY, self.ENTRY_SIG, self.DAO_SIG]:
            assert _sanitize_id(sig) in dot

    def test_all_three_edges_rendered(self):
        from calltree_to_dot import collect_nodes_flat, collect_edges_flat, find_roots, render_dot, _make_dot_label, _sanitize_id

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {sig: _make_dot_label(nd) for sig, nd in nodes.items()}
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert f"{_sanitize_id(self.JSP_KEY)} -> {_sanitize_id(self.EL_KEY)}" in dot
        assert f"{_sanitize_id(self.EL_KEY)} -> {_sanitize_id(self.ENTRY_SIG)}" in dot
        assert f"{_sanitize_id(self.ENTRY_SIG)} -> {_sanitize_id(self.DAO_SIG)}" in dot

    def test_edge_info_typed_edges_not_filtered(self):
        from calltree_to_dot import collect_edges_flat

        nodes, calls = self._make_data()
        edges, cycle_edges = collect_edges_flat(calls)
        assert (self.JSP_KEY, self.EL_KEY) in edges
        assert (self.EL_KEY, self.ENTRY_SIG) in edges
        assert (self.ENTRY_SIG, self.DAO_SIG) in edges

    def test_jsp_node_is_root(self):
        from calltree_to_dot import collect_nodes_flat, find_roots

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        roots = find_roots(node_sigs, calls)
        assert self.JSP_KEY in roots

    def test_dot_output_is_valid_digraph(self):
        from calltree_to_dot import collect_nodes_flat, collect_edges_flat, find_roots, render_dot, _make_dot_label

        nodes, calls = self._make_data()
        node_sigs = collect_nodes_flat(nodes)
        edges, cycle_edges = collect_edges_flat(calls)
        roots = find_roots(node_sigs, calls)
        label_map = {sig: _make_dot_label(nd) for sig, nd in nodes.items()}
        dot = render_dot(node_sigs, edges, cycle_edges, label_map, roots)

        assert dot.startswith("digraph")
        assert dot.strip().endswith("}")
```

- [ ] **Step 2: Run new tests**

```bash
cd python && uv run pytest tests/test_calltree_to_dot.py -v
```

Expected: all tests pass (calltree_to_dot.py requires no changes).

- [ ] **Step 3: Commit**

```bash
cd python && git add tests/test_calltree_to_dot.py
git commit -m "test: add calltree-to-dot producer-scenario tests for calltree, frames, jspmap"
```

---

## Task 5: Delete `jspmap_to_dot.py` and its test; update pyproject.toml

**Files:**
- Delete: `python/jspmap_to_dot.py`
- Delete: `python/tests/test_jspmap_to_dot.py`
- Modify: `python/pyproject.toml`

- [ ] **Step 1: Delete the two files**

```bash
cd python && rm jspmap_to_dot.py tests/test_jspmap_to_dot.py
```

- [ ] **Step 2: Remove `jspmap-to-dot` from `python/pyproject.toml`**

In `[project.scripts]`, remove the line:
```
jspmap-to-dot = "jspmap_to_dot:main"
```

- [ ] **Step 3: Run full test suite to confirm no breakage**

```bash
cd python && uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
cd python && git add -u
git commit -m "feat: delete jspmap_to_dot; remove from pyproject.toml"
```

Note: `git add -u` stages deletions and modifications but not untracked new files.

---

## Task 6: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the tool list description**

In the tool list (around line 39), change:
```
- `jspmap`: map JSP EL actions through call graph to DAO methods; outputs JSON semantic map
- `jspmap-to-dot`: render jspmap JSON output as DOT/SVG
```
to:
```
- `jspmap`: map JSP EL actions through a call graph; emits flat {nodes, calls, metadata} consumable by calltree-print, frames-print, calltree-to-dot
```

- [ ] **Step 2: Update the Tool Combinations diagram**

Replace the current diagram (lines ~44–71):

```
## Tool Combinations

```text
classpath
    |
    +---> dump ------------------------------------------------> method ranges
    |
    +---> trace -----------------------------------------------> intra-method paths
    |
    +---> buildcg ---------------------------------------------> call graph JSON
                                                                       |
                +-----------------------+------------------+-----------+
                |                       |                  |
             calltree               frames              jspmap
                \                   /                   /
                 \                 /                   /
                  v               v                   v
           flat {nodes, calls, metadata}
                       |
         +-------------+-------------+
         |             |             |
  calltree-print  frames-print  calltree-to-dot
    (ASCII)         (text)        (SVG/DOT)
                                                                 |
    +---> xtrace* ---------------------------------------------> envelope JSON
                                                              [ftrace-slice]
                                                          [ftrace-expand-refs]
                                                              ftrace-semantic
                                                                   |
                                                     +-------------+-------------+
                                                     |                           |
                                           ftrace-semantic-to-dot     ftrace-validate
                                                     |
                                                  SVG/DOT

* also takes classpath directly
```

- [ ] **Step 3: Verify the README renders without orphaned headings**

```bash
grep -n "jspmap-to-dot" README.md
```

Expected: no matches.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README — jspmap now emits flat schema; remove jspmap-to-dot"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: All spec sections covered: `node_type`/`edge_info` on calltree+frames (Tasks 1–2); jspmap flat schema rewrite (Task 3); calltree-to-dot tests for all three producers (Task 4); deletions (Task 5); README (Task 6).
- [x] **No placeholders**: All steps contain complete code.
- [x] **Type consistency**: `_graft_action()` signature matches its call site in `run()`; `_calltree_build_graph` alias matches `build_graph` signature throughout.
- [x] **TDD order**: Tests written before implementation in every task.
- [x] **Breaking changes acknowledged**: Tasks 1+2 are breaking schema changes; any consumer asserting exact output shape must be updated — covered by the test rewrites in Tasks 1–4.
