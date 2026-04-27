# Decompose build_dot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `build_dot` in `python/ftrace_to_dot.py` from a 127-line function with nested mutable `add_method` into pure extracted functions following FP style.

**Architecture:** Extract `_render_leaf`, `_render_trap_cluster`, `_render_cross_edges` as pure functions. Replace nested `add_method` with recursive `_render_method` that threads a counter and returns `_MethodDotResult`. `build_dot` becomes a thin orchestrator: header + `_render_method(root, 0)` + cross_edges + footer.

**Tech Stack:** Python 3.13+, pytest, TypedDict

---

## File Structure

| File | Responsibility |
|------|---------------|
| `python/ftrace_to_dot.py` | DOT rendering — extract functions, add `_MethodDotResult`, refactor `build_dot` |
| `python/tests/test_dot_rendering.py` | Unit tests for extracted functions + existing integration tests |

---

### Task 1: `_MethodDotResult` TypedDict and `_render_leaf`

**Files:**
- Modify: `python/ftrace_to_dot.py:1-22` (imports), `python/ftrace_to_dot.py:107-141` (leaf logic)
- Modify: `python/tests/test_dot_rendering.py` (add test class)

- [ ] **Step 1: Write failing tests for `_render_leaf`**

Add this test class at the end of `python/tests/test_dot_rendering.py`:

```python
class TestRenderLeaf:
    def test_ref_leaf(self):
        from ftrace_to_dot import _render_leaf

        node = {"class": "com.example.Svc", "method": "run", "ref": True}
        lines, nid, next_counter = _render_leaf(node, 5)
        assert len(lines) == 1
        assert "n_leaf_5" in lines[0]
        assert "(ref)" in lines[0]
        assert "#e8e8e8" in lines[0]
        assert nid == "n_leaf_5"
        assert next_counter == 6

    def test_cycle_leaf(self):
        from ftrace_to_dot import _render_leaf

        node = {"class": "com.example.Svc", "method": "run", "cycle": True}
        lines, nid, next_counter = _render_leaf(node, 0)
        assert len(lines) == 1
        assert "n_leaf_0" in lines[0]
        assert "(cycle)" in lines[0]
        assert "#ffcccc" in lines[0]
        assert nid == "n_leaf_0"
        assert next_counter == 1

    def test_filtered_leaf(self):
        from ftrace_to_dot import _render_leaf

        node = {"class": "com.example.Svc", "method": "run", "filtered": True}
        lines, nid, next_counter = _render_leaf(node, 3)
        assert len(lines) == 1
        assert "(filtered)" in lines[0]
        assert "#fff3cd" in lines[0]
        assert nid == "n_leaf_3"
        assert next_counter == 4

    def test_non_leaf_returns_empty(self):
        from ftrace_to_dot import _render_leaf

        node = {"class": "com.example.Svc", "method": "run"}
        lines, nid, next_counter = _render_leaf(node, 7)
        assert lines == []
        assert nid == ""
        assert next_counter == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/test_dot_rendering.py::TestRenderLeaf -v`
Expected: FAIL with `ImportError: cannot import name '_render_leaf'`

- [ ] **Step 3: Add `_MethodDotResult` TypedDict and implement `_render_leaf`**

In `python/ftrace_to_dot.py`, add `TypedDict` to the `typing` import (currently no typing import exists, so add one) and add the TypedDict + function after the existing `_render_exception_edge` function (after line 104, before `build_dot`):

```python
from typing import TypedDict
```

Then after `_render_exception_edge` (line 104):

```python
class _MethodDotResult(TypedDict):
    lines: list[str]
    cross_edges: list[str]
    next_counter: int
    entry_nid: str


def _render_leaf(node: MethodSemanticCFG, counter: int) -> tuple[list[str], str, int]:
    """Render a leaf node (ref/cycle/filtered). Returns (lines, nid, next_counter).

    Returns ([], "", counter) if node is not a leaf.
    """
    cls = short_class(node.get("class", "?"))
    method = node.get("method", "?")
    leaf_kind = next(
        (k for k in ("cycle", "ref", "filtered") if node.get(k, False)),
        "",
    )
    if not leaf_kind:
        return ([], "", counter)
    nid = f"n_leaf_{counter}"
    label = f"{cls}.{method}\\n({leaf_kind})"
    style = NODE_STYLE[NodeKind(leaf_kind)]
    attrs = f'label="{escape(label)}"'
    attrs += "".join(f', {k}="{v}"' for k, v in style.items())
    return ([f"  {nid} [{attrs}];"], nid, counter + 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/test_dot_rendering.py::TestRenderLeaf -v`
Expected: 4 passed

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/test_dot_rendering.py -v`
Expected: All 17 existing + 4 new = 21 passed

- [ ] **Step 6: Commit**

```bash
git add python/ftrace_to_dot.py python/tests/test_dot_rendering.py
git commit -m "feat: add _MethodDotResult TypedDict and _render_leaf"
```

---

### Task 2: `_render_trap_cluster`

**Files:**
- Modify: `python/ftrace_to_dot.py` (add function after `_render_leaf`)
- Modify: `python/tests/test_dot_rendering.py` (add test class)

- [ ] **Step 1: Write failing tests for `_render_trap_cluster`**

Add this test class at the end of `python/tests/test_dot_rendering.py`:

```python
class TestRenderTrapCluster:
    def test_try_cluster(self):
        from ftrace_to_dot import _render_trap_cluster

        cluster = {"trapType": "RuntimeException", "role": "try", "nodeIds": ["n0", "n1"]}
        lines = _render_trap_cluster(0, cluster)
        assert "subgraph cluster_trap_0 {" in lines[0]
        assert 'try (RuntimeException)' in lines[1]
        assert "#ffa500" in lines[2]
        assert "n0;" in lines[3]
        assert "n1;" in lines[4]
        assert lines[-1] == "    }"

    def test_handler_catch(self):
        from ftrace_to_dot import _render_trap_cluster

        cluster = {
            "trapType": "RuntimeException",
            "role": "handler",
            "nodeIds": ["n2"],
            "entryNodeId": "n2",
        }
        lines = _render_trap_cluster(1, cluster)
        assert "subgraph cluster_trap_1 {" in lines[0]
        assert 'catch (RuntimeException)' in lines[1]
        assert "#007bff" in lines[2]
        assert "n2;" in lines[3]
        assert lines[-1] == "    }"

    def test_handler_finally_throwable(self):
        from ftrace_to_dot import _render_trap_cluster

        cluster = {
            "trapType": "Throwable",
            "role": "handler",
            "nodeIds": ["n3"],
            "entryNodeId": "n3",
        }
        lines = _render_trap_cluster(2, cluster)
        assert "finally" in lines[1]
        assert "#007bff" in lines[2]

    def test_handler_finally_any(self):
        from ftrace_to_dot import _render_trap_cluster

        cluster = {
            "trapType": "any",
            "role": "handler",
            "nodeIds": ["n4"],
            "entryNodeId": "n4",
        }
        lines = _render_trap_cluster(3, cluster)
        assert "finally" in lines[1]

    def test_empty_node_ids(self):
        from ftrace_to_dot import _render_trap_cluster

        cluster = {"trapType": "IOException", "role": "try", "nodeIds": []}
        lines = _render_trap_cluster(0, cluster)
        assert lines[0] == "    subgraph cluster_trap_0 {"
        assert lines[-1] == "    }"
        # Only header (1) + label (1) + style (1) + footer (1) = 4 lines
        assert len(lines) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/test_dot_rendering.py::TestRenderTrapCluster -v`
Expected: FAIL with `ImportError: cannot import name '_render_trap_cluster'`

- [ ] **Step 3: Implement `_render_trap_cluster`**

In `python/ftrace_to_dot.py`, add after `_render_leaf`:

```python
def _render_trap_cluster(index: int, cluster: SemanticCluster) -> list[str]:
    """Render one trap cluster as a DOT subgraph."""
    trap_type = cluster["trapType"]
    role = cluster["role"]
    node_ids = cluster.get("nodeIds", [])

    tc_id = f"cluster_trap_{index}"
    header = [f"    subgraph {tc_id} {{"]

    if role == "try":
        style_lines = [
            f'      label="try ({escape(trap_type)})";',
            '      style="dashed,rounded"; color="#ffa500"; fontcolor="#ffa500";',
        ]
    else:
        h_label = (
            "finally"
            if trap_type.lower() in ("throwable", "any")
            else f"catch ({escape(trap_type)})"
        )
        style_lines = [
            f'      label="{h_label}";',
            '      style="dashed,rounded"; color="#007bff"; fontcolor="#007bff";',
        ]

    node_lines = [f"      {nid};" for nid in node_ids]
    return [*header, *style_lines, *node_lines, "    }"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/test_dot_rendering.py::TestRenderTrapCluster -v`
Expected: 5 passed

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/test_dot_rendering.py -v`
Expected: All 26 passed (17 existing + 4 from Task 1 + 5 new)

- [ ] **Step 6: Commit**

```bash
git add python/ftrace_to_dot.py python/tests/test_dot_rendering.py
git commit -m "feat: extract _render_trap_cluster as pure function"
```

---

### Task 3: `_render_cross_edges`

**Files:**
- Modify: `python/ftrace_to_dot.py` (add function after `_render_trap_cluster`)
- Modify: `python/tests/test_dot_rendering.py` (add test class)

- [ ] **Step 1: Write failing tests for `_render_cross_edges`**

Add this test class at the end of `python/tests/test_dot_rendering.py`:

```python
class TestRenderCrossEdges:
    def test_matching_call_site_line(self):
        from ftrace_to_dot import _render_cross_edges

        nodes = [
            {"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]},
            {"id": "n1", "lines": [9], "kind": "call", "label": ["L9", "Other.run"]},
        ]
        children = [{"callSiteLine": 9, "method": "run"}]
        child_entries = ["n5"]
        result = _render_cross_edges(nodes, children, child_entries, "n0")
        assert len(result) == 1
        assert "n1 -> n5" in result[0]
        assert "#e05050" in result[0]
        assert "bold" in result[0]

    def test_fallback_to_entry_nid(self):
        from ftrace_to_dot import _render_cross_edges

        nodes = [
            {"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]},
        ]
        children = [{"callSiteLine": 99, "method": "run"}]
        child_entries = ["n5"]
        result = _render_cross_edges(nodes, children, child_entries, "n0")
        assert len(result) == 1
        assert "n0 -> n5" in result[0]

    def test_empty_child_entry_skipped(self):
        from ftrace_to_dot import _render_cross_edges

        nodes = [{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}]
        children = [{"callSiteLine": 5, "method": "run"}]
        child_entries = [""]
        result = _render_cross_edges(nodes, children, child_entries, "n0")
        assert result == []

    def test_no_children(self):
        from ftrace_to_dot import _render_cross_edges

        nodes = [{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}]
        result = _render_cross_edges(nodes, [], [], "n0")
        assert result == []

    def test_no_entry_nid_no_match(self):
        from ftrace_to_dot import _render_cross_edges

        nodes = [{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}]
        children = [{"callSiteLine": 99, "method": "run"}]
        child_entries = ["n5"]
        result = _render_cross_edges(nodes, children, child_entries, "")
        assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/test_dot_rendering.py::TestRenderCrossEdges -v`
Expected: FAIL with `ImportError: cannot import name '_render_cross_edges'`

- [ ] **Step 3: Implement `_render_cross_edges`**

In `python/ftrace_to_dot.py`, add `from functools import reduce` at the top (after the existing imports). Then add after `_render_trap_cluster`:

```python
def _render_cross_edges(
    nodes: list[SemanticNode],
    children: list[MethodSemanticCFG],
    child_entries: list[str],
    entry_nid: str,
) -> list[str]:
    """Build parent→child call edges by matching callSiteLine to node lines."""
    line_to_nids: dict[int, list[str]] = reduce(
        lambda acc, pair: {**acc, pair[0]: [*acc.get(pair[0], []), pair[1]]},
        ((ln, n["id"]) for n in nodes for ln in n.get("lines", [])),
        {},
    )

    def _edge_for_child(child: MethodSemanticCFG, child_entry: str) -> list[str]:
        if not child_entry:
            return []
        csl = child.get("callSiteLine", -1)
        source_nids = line_to_nids.get(csl, [])
        if source_nids:
            return [
                f"  {source_nids[0]} -> {child_entry} "
                f'[color="#e05050", style=bold, penwidth=1.5];'
            ]
        if entry_nid:
            return [f"  {entry_nid} -> {child_entry};"]
        return []

    return [
        line
        for child, child_entry in zip(children, child_entries)
        for line in _edge_for_child(child, child_entry)
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/test_dot_rendering.py::TestRenderCrossEdges -v`
Expected: 5 passed

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/test_dot_rendering.py -v`
Expected: All 31 passed (26 prior + 5 new)

- [ ] **Step 6: Commit**

```bash
git add python/ftrace_to_dot.py python/tests/test_dot_rendering.py
git commit -m "feat: extract _render_cross_edges as pure function"
```

---

### Task 4: `_render_method` and `build_dot` orchestrator refactor

**Files:**
- Modify: `python/ftrace_to_dot.py:107-233` (replace `build_dot` internals)

No new tests — existing 17 integration tests + 14 unit tests verify correctness.

- [ ] **Step 1: Replace `build_dot` with `_render_method` + thin orchestrator**

Replace the entire `build_dot` function (lines 107-233, adjusted for earlier insertions) with:

```python
def _render_method(node: MethodSemanticCFG, counter: int) -> _MethodDotResult:
    """Recursively render a method and its children as DOT lines."""
    # Leaf check
    leaf_kind = next(
        (k for k in ("cycle", "ref", "filtered") if node.get(k, False)),
        "",
    )
    if leaf_kind:
        leaf_lines, nid, next_counter = _render_leaf(node, counter)
        return {
            "lines": leaf_lines,
            "cross_edges": [],
            "next_counter": next_counter,
            "entry_nid": nid,
        }

    # Extract fields
    cls = short_class(node.get("class", "?"))
    method_name = node.get("method", "?")
    nodes = node.get("nodes", [])
    edges = node.get("edges", [])
    clusters = node.get("clusters", [])
    exception_edges = node.get("exceptionEdges", [])
    children = node.get("children", [])
    line_start = node.get("lineStart", "?")
    line_end = node.get("lineEnd", "?")
    entry_nid = node.get("entryNodeId", "") or (nodes[0]["id"] if nodes else "")

    # Subgraph for this method
    cid = f"cluster_{counter}"
    subgraph = [
        f"  subgraph {cid} {{",
        f'    label="{escape(cls)}.{escape(method_name)} [{line_start}-{line_end}]";',
        '    style="rounded,filled"; fillcolor="#f0f0f0";',
        '    color="#4a86c8";',
        "",
        *[_render_node(n["id"], n) for n in nodes],
        *[_render_edge(e) for e in edges],
        *[line for i, c in enumerate(clusters) for line in _render_trap_cluster(i, c)],
        *[_render_exception_edge(ee, clusters) for ee in exception_edges],
        "  }",
        "",
    ]

    # Recurse children, threading counter
    def _fold_child(
        acc: dict[str, list[_MethodDotResult] | int],
        child: MethodSemanticCFG,
    ) -> dict[str, list[_MethodDotResult] | int]:
        result = _render_method(child, acc["counter"])
        return {
            "results": [*acc["results"], result],
            "counter": result["next_counter"],
        }

    folded = reduce(
        _fold_child,
        children,
        {"results": [], "counter": counter + 1},
    )

    child_results: list[_MethodDotResult] = folded["results"]
    child_lines = [line for r in child_results for line in r["lines"]]
    child_cross = [edge for r in child_results for edge in r["cross_edges"]]
    child_entries = [r["entry_nid"] for r in child_results]

    cross_edges = [
        *child_cross,
        *_render_cross_edges(nodes, children, child_entries, entry_nid),
    ]

    return {
        "lines": [*subgraph, *child_lines],
        "cross_edges": cross_edges,
        "next_counter": folded["counter"],
        "entry_nid": entry_nid,
    }


def build_dot(root: MethodSemanticCFG) -> str:
    """Render a MethodSemanticCFG tree as a Graphviz DOT string."""
    header = [
        "digraph ftrace {",
        "  rankdir=TB;",
        "  compound=true;",
        '  node [shape=box, style="filled,rounded", fillcolor=white, '
        'fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
        "",
    ]
    result = _render_method(root, 0)
    footer = ["  // Cross-cluster call edges", *result["cross_edges"], "}"]
    return "\n".join([*header, *result["lines"], *footer])
```

- [ ] **Step 2: Run unit tests**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/test_dot_rendering.py -v`
Expected: All 31 passed

- [ ] **Step 3: Run full Python test suite**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Run E2E tests**

Run: `cd /Users/asgupta/code/java-bytecode-tools/test-fixtures && bash run-e2e.sh`
Expected: All E2E tests pass

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_to_dot.py
git commit -m "refactor: decompose build_dot into pure FP functions"
```
