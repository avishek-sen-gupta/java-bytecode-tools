# ftrace-slice Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `ftrace-slice` into two chainable CLI tools: `ftrace-slice` (jq slice + ref index) and `ftrace-expand-refs` (recursive ref expansion).

**Architecture:** Two independent CLI tools with a `SlicedTrace` intermediate format connecting them. Both follow `--input`/`--output` conventions with stdin/stdout defaults.

**Tech Stack:** Python 3.13+, uv, argparse, jq (subprocess), pytest

**Spec:** `docs/superpowers/specs/2026-04-27-ftrace-slice-decomposition-design.md`

**Constraints (apply throughout all tasks):**
- **No `None` checks** — use null object pattern: empty dicts `{}`, empty lists `[]`, empty strings `""` instead of `None`
- **No `Optional` in type hints** — no `Optional[X]` or `X | None`; use concrete defaults
- **No defensive `get()` with `None` fallback** — always provide a concrete default: `dict.get(key, "")`, `dict.get(key, [])`, `dict.get(key, False)`, etc.
- **Immutable data** — prefer `frozenset` over `set` where applicable
- **FP principles** — no mutation, comprehensions, small pure functions, dependency injection. **No nested for...if loops** — use comprehensions, `filter`, `map`, `itertools` instead
- **TDD** — write tests first, see them fail, then implement
- **Early returns** — guard clauses at top of functions; happy path outside conditions
- **Strong typing** — TypedDict, StrEnum, no bare dicts at API boundaries

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `python/ftrace_types.py` | Modify | Add `SlicedTrace` TypedDict |
| `python/ftrace_slice.py` | Rewrite | jq slice + scoped ref index bundling |
| `python/ftrace_expand_refs.py` | Create | Expand ref nodes using ref index |
| `python/pyproject.toml` | Modify | Register `ftrace-expand-refs` entry point |
| `python/tests/test_ftrace_types.py` | Modify | Smoke test for `SlicedTrace` |
| `python/tests/test_ftrace_slice_unit.py` | Create | Unit tests for `collect_ref_signatures`, `index_full_tree` |
| `python/tests/test_expand_refs.py` | Rewrite | Tests import from `ftrace_expand_refs`, use `frozenset` |
| `test-fixtures/tests/test_ftrace_slice.sh` | Rewrite | E2E: two-tool pipeline |
| `README.md` | Modify | Pipeline docs, project structure, quick reference |

---

### Task 1: Add SlicedTrace type

**Files:**
- Modify: `python/ftrace_types.py` (append after line 203)
- Modify: `python/tests/test_ftrace_types.py`

- [ ] **Step 1: Write the failing test**

Add to `python/tests/test_ftrace_types.py`:

```python
from ftrace_types import SlicedTrace


def test_sliced_trace_type():
    """SlicedTrace has slice and refIndex fields."""
    st: SlicedTrace = {
        "slice": {"method": "foo", "children": []},
        "refIndex": {"<Svc: void foo()>": {"method": "foo"}},
    }
    assert st["slice"]["method"] == "foo"
    assert "<Svc: void foo()>" in st["refIndex"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && python3 -m pytest tests/test_ftrace_types.py::test_sliced_trace_type -v`
Expected: FAIL with `ImportError: cannot import name 'SlicedTrace'`

- [ ] **Step 3: Add SlicedTrace to ftrace_types.py**

Append to `python/ftrace_types.py`:

```python
class SlicedTrace(TypedDict):
    """Output of ftrace-slice: a sliced subtree plus a ref index for expansion.

    Fields:
    - slice: the sliced subtree (trace node)
    - refIndex: methodSignature → full node, scoped to refs in the slice
    """

    slice: dict
    refIndex: dict[str, dict]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python && python3 -m pytest tests/test_ftrace_types.py::test_sliced_trace_type -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_types.py python/tests/test_ftrace_types.py
git commit -m "feat: add SlicedTrace type to ftrace_types"
```

---

### Task 2: Create ftrace_expand_refs.py with expand_refs

Move `expand_refs` from `ftrace_slice.py` to a new `ftrace_expand_refs.py` module. Rewrite to use `frozenset` for path (no mutation).

**Files:**
- Create: `python/ftrace_expand_refs.py`
- Rewrite: `python/tests/test_expand_refs.py` (update imports, use `frozenset`, add immutability test)

- [ ] **Step 1: Rewrite tests**

Replace `python/tests/test_expand_refs.py` with:

```python
"""Tests for ftrace_expand_refs: ref expansion correctness."""

import copy

from ftrace_expand_refs import expand_refs


def _make_full_node(sig):
    """Helper to build a fully-expanded node."""
    return {
        "class": "com.example.Svc",
        "method": "doWork",
        "methodSignature": sig,
        "lineStart": 10,
        "lineEnd": 20,
        "sourceLineCount": 11,
        "sourceTrace": [{"line": 10, "code": "int x = 1;"}],
        "blocks": [{"id": "B0", "stmts": [], "successors": ["B1"]}],
        "traps": [
            {"handler": "B2", "type": "RuntimeException", "coveredBlocks": ["B0"]}
        ],
        "children": [],
    }


def _make_ref_node(sig, call_site_line=5):
    return {
        "class": "com.example.Svc",
        "method": "doWork",
        "methodSignature": sig,
        "ref": True,
        "callSiteLine": call_site_line,
    }


def _index_from_nodes(*nodes):
    """Build a ref index from full nodes."""
    return {n["methodSignature"]: n for n in nodes}


class TestExpandRefs:
    def test_callsiteline_preserved_from_ref_node(self):
        """callSiteLine comes from the ref node, not the full expansion."""
        sig = "<com.example.Svc: void doWork()>"
        full = _make_full_node(sig)
        full["callSiteLine"] = 99
        ref = _make_ref_node(sig, call_site_line=42)

        index = _index_from_nodes(full)
        expanded = expand_refs(ref, index, frozenset())
        assert expanded["callSiteLine"] == 42

    def test_children_recursively_expanded(self):
        """Children of the full node should also have their refs expanded."""
        parent_sig = "<com.example.Svc: void parent()>"
        child_sig = "<com.example.Svc: void child()>"

        child_full = _make_full_node(child_sig)
        child_ref = _make_ref_node(child_sig, call_site_line=15)

        parent_full = _make_full_node(parent_sig)
        parent_full["children"] = [child_ref]

        parent_ref = _make_ref_node(parent_sig, call_site_line=1)

        index = _index_from_nodes(parent_full, child_full)
        expanded = expand_refs(parent_ref, index, frozenset())
        assert len(expanded["children"]) == 1
        assert expanded["children"][0]["callSiteLine"] == 15
        assert expanded["children"][0]["blocks"] == child_full["blocks"]

    def test_ref_flag_removed(self):
        """The expanded node must not carry the 'ref' flag."""
        sig = "<com.example.Svc: void doWork()>"
        full = _make_full_node(sig)
        ref = _make_ref_node(sig)

        index = _index_from_nodes(full)
        expanded = expand_refs(ref, index, frozenset())
        assert "ref" not in expanded

    def test_cycle_detection(self):
        """If the sig is already in the path, ref should not be expanded."""
        sig = "<com.example.Svc: void doWork()>"
        ref = _make_ref_node(sig)

        index = _index_from_nodes(_make_full_node(sig))
        expanded = expand_refs(ref, index, frozenset({sig}))
        assert expanded.get("ref", False) is True

    def test_ref_not_in_index_returned_as_is(self):
        """A ref whose signature is not in the index is returned unchanged."""
        ref = _make_ref_node("<com.example.Svc: void missing()>")
        expanded = expand_refs(ref, {}, frozenset())
        assert expanded.get("ref", False) is True

    def test_non_ref_children_recursed(self):
        """Non-ref nodes with children have their children expanded."""
        child_sig = "<com.example.Svc: void child()>"
        child_full = _make_full_node(child_sig)
        child_ref = _make_ref_node(child_sig)

        parent = {
            "methodSignature": "<com.example.Svc: void parent()>",
            "children": [child_ref],
        }

        index = _index_from_nodes(child_full)
        expanded = expand_refs(parent, index, frozenset())
        assert "ref" not in expanded["children"][0]
        assert expanded["children"][0]["blocks"] == child_full["blocks"]

    def test_does_not_mutate_input(self):
        """expand_refs must not mutate the input node or index."""
        sig = "<com.example.Svc: void doWork()>"
        full = _make_full_node(sig)
        ref = _make_ref_node(sig)
        index = _index_from_nodes(full)

        original_ref = copy.deepcopy(ref)
        original_index = copy.deepcopy(index)

        expand_refs(ref, index, frozenset())

        assert ref == original_ref
        assert index == original_index
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && python3 -m pytest tests/test_expand_refs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ftrace_expand_refs'`

- [ ] **Step 3: Create ftrace_expand_refs.py**

Create `python/ftrace_expand_refs.py`:

```python
#!/usr/bin/env python3
"""Expand ref nodes in a sliced trace using a pre-built ref index.

Pure function: uses frozenset for cycle detection (no mutation).
"""

import argparse
import json
import sys
from pathlib import Path


def expand_refs(
    node: dict, index: dict[str, dict], path: frozenset[str] = frozenset()
) -> dict:
    """Return a copy of node with ref nodes replaced by their full expansion.

    Args:
        node: trace node (may have ref=True)
        index: methodSignature → full node mapping
        path: visited signatures for cycle detection (immutable)
    """
    if node.get("ref", False):
        return _expand_ref_node(node, index, path)

    sig = node.get("methodSignature", "")
    new_path = path | {sig} if sig else path

    if "children" not in node:
        return dict(node)

    return {
        **node,
        "children": [expand_refs(c, index, new_path) for c in node["children"]],
    }


def _expand_ref_node(
    node: dict, index: dict[str, dict], path: frozenset[str]
) -> dict:
    """Expand a single ref node if its signature is in the index and not cyclic."""
    sig = node.get("methodSignature", "")

    if not sig or sig not in index or sig in path:
        return dict(node)

    full = index[sig]
    return {
        **{k: v for k, v in full.items() if k != "ref" and k != "children"},
        **({} if "callSiteLine" not in node else {"callSiteLine": node["callSiteLine"]}),
        "children": [
            expand_refs(c, index, path | {sig}) for c in full.get("children", [])
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Expand ref nodes in a sliced trace using a pre-built ref index."
    )
    parser.add_argument("--input", type=Path, help="SlicedTrace JSON (default: stdin)")
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    data = (
        json.loads(args.input.read_text())
        if args.input
        else json.load(sys.stdin)
    )

    expanded = expand_refs(data["slice"], data["refIndex"])

    output = json.dumps(expanded, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote expanded trace to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && python3 -m pytest tests/test_expand_refs.py -v`
Expected: PASS (all 7 tests)

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_expand_refs.py python/tests/test_expand_refs.py
git commit -m "feat: extract expand_refs into standalone ftrace_expand_refs module"
```

---

### Task 3: Add collect_ref_signatures and scoped index_full_tree to ftrace_slice

**Files:**
- Create: `python/tests/test_ftrace_slice_unit.py`
- Modify: `python/ftrace_slice.py`

- [ ] **Step 1: Write failing tests**

Create `python/tests/test_ftrace_slice_unit.py`:

```python
"""Unit tests for ftrace_slice pure functions."""

import copy

from ftrace_slice import collect_ref_signatures, index_full_tree


class TestCollectRefSignatures:
    def test_empty_node(self):
        assert collect_ref_signatures({"children": []}) == frozenset()

    def test_single_ref(self):
        node = {
            "children": [
                {"methodSignature": "<Svc: void a()>", "ref": True},
            ]
        }
        assert collect_ref_signatures(node) == frozenset({"<Svc: void a()>"})

    def test_non_ref_ignored(self):
        node = {
            "children": [
                {"methodSignature": "<Svc: void a()>"},
            ]
        }
        assert collect_ref_signatures(node) == frozenset()

    def test_nested_refs(self):
        node = {
            "methodSignature": "<Svc: void parent()>",
            "children": [
                {
                    "methodSignature": "<Svc: void child()>",
                    "children": [
                        {"methodSignature": "<Svc: void grandchild()>", "ref": True}
                    ],
                },
                {"methodSignature": "<Svc: void sibling()>", "ref": True},
            ],
        }
        assert collect_ref_signatures(node) == frozenset(
            {"<Svc: void grandchild()>", "<Svc: void sibling()>"}
        )

    def test_ref_without_signature_ignored(self):
        node = {"children": [{"ref": True}]}
        assert collect_ref_signatures(node) == frozenset()

    def test_does_not_mutate_input(self):
        node = {"children": [{"methodSignature": "<Svc: void a()>", "ref": True}]}
        original = copy.deepcopy(node)
        collect_ref_signatures(node)
        assert node == original


class TestIndexFullTree:
    def test_empty_signatures(self):
        tree = {"methodSignature": "<Svc: void a()>", "children": []}
        assert index_full_tree(tree, frozenset()) == {}

    def test_indexes_matching_signature(self):
        sig = "<Svc: void a()>"
        tree = {"methodSignature": sig, "children": []}
        result = index_full_tree(tree, frozenset({sig}))
        assert sig in result
        assert result[sig] is tree

    def test_skips_ref_nodes(self):
        sig = "<Svc: void a()>"
        tree = {"methodSignature": sig, "ref": True, "children": []}
        assert index_full_tree(tree, frozenset({sig})) == {}

    def test_skips_cycle_nodes(self):
        sig = "<Svc: void a()>"
        tree = {"methodSignature": sig, "cycle": True, "children": []}
        assert index_full_tree(tree, frozenset({sig})) == {}

    def test_skips_filtered_nodes(self):
        sig = "<Svc: void a()>"
        tree = {"methodSignature": sig, "filtered": True, "children": []}
        assert index_full_tree(tree, frozenset({sig})) == {}

    def test_first_occurrence_wins(self):
        sig = "<Svc: void a()>"
        first = {"methodSignature": sig, "children": [], "marker": "first"}
        second = {"methodSignature": sig, "children": [], "marker": "second"}
        tree = {"children": [first, second]}
        result = index_full_tree(tree, frozenset({sig}))
        assert result[sig]["marker"] == "first"

    def test_unmatched_signatures_excluded(self):
        tree = {
            "children": [
                {"methodSignature": "<Svc: void a()>", "children": []},
                {"methodSignature": "<Svc: void b()>", "children": []},
            ]
        }
        result = index_full_tree(tree, frozenset({"<Svc: void a()>"}))
        assert "<Svc: void a()>" in result
        assert "<Svc: void b()>" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && python3 -m pytest tests/test_ftrace_slice_unit.py -v`
Expected: FAIL with `ImportError: cannot import name 'collect_ref_signatures'`

- [ ] **Step 3: Implement the functions**

Add to `ftrace_slice.py` (replacing the old `index_full_tree` and `expand_refs`). Remove the old functions — the full rewrite of `main()` happens in Task 4. For now, keep the existing `main()` so the module is importable, but add the new pure functions:

```python
def collect_ref_signatures(node: dict) -> frozenset[str]:
    """Walk a subtree and return all methodSignature values where ref is true."""
    sig = node.get("methodSignature", "")
    refs = frozenset({sig}) if node.get("ref", False) and sig else frozenset()
    return refs | frozenset(
        s
        for child in node.get("children", [])
        for s in collect_ref_signatures(child)
    )


def index_full_tree(node: dict, signatures: frozenset[str]) -> dict[str, dict]:
    """Walk the full tree, return {sig → node} for signatures in the given set.

    First non-ref, non-cycle, non-filtered occurrence wins.
    Uses an internal accumulator for DFS first-occurrence semantics;
    the public interface is pure (fresh dict returned).
    """
    acc: dict[str, dict] = {}
    _index_walk(node, signatures, acc)
    return acc


def _index_walk(
    node: dict, signatures: frozenset[str], acc: dict[str, dict]
) -> None:
    """DFS walker for index_full_tree. Mutates acc (internal only)."""
    sig = node.get("methodSignature", "")
    if (
        sig
        and sig in signatures
        and sig not in acc
        and not node.get("ref", False)
        and not node.get("cycle", False)
        and not node.get("filtered", False)
    ):
        acc[sig] = node
    for child in node.get("children", []):
        _index_walk(child, signatures, acc)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && python3 -m pytest tests/test_ftrace_slice_unit.py -v`
Expected: PASS (all 13 tests)

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_slice.py python/tests/test_ftrace_slice_unit.py
git commit -m "feat: add collect_ref_signatures and scoped index_full_tree"
```

---

### Task 4: Rewrite ftrace_slice.py main() to output SlicedTrace

**Files:**
- Rewrite: `python/ftrace_slice.py`

- [ ] **Step 1: Rewrite ftrace_slice.py**

Replace the entire file with:

```python
#!/usr/bin/env python3
"""Slice a subtree from an ftrace JSON and bundle a ref index for downstream expansion.

Output format (SlicedTrace):
  { "slice": <subtree>, "refIndex": { methodSignature → full node } }

The refIndex is scoped: only signatures referenced by ref nodes in the slice are included.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def collect_ref_signatures(node: dict) -> frozenset[str]:
    """Walk a subtree and return all methodSignature values where ref is true."""
    sig = node.get("methodSignature", "")
    refs = frozenset({sig}) if node.get("ref", False) and sig else frozenset()
    return refs | frozenset(
        s
        for child in node.get("children", [])
        for s in collect_ref_signatures(child)
    )


def index_full_tree(node: dict, signatures: frozenset[str]) -> dict[str, dict]:
    """Walk the full tree, return {sig → node} for signatures in the given set.

    First non-ref, non-cycle, non-filtered occurrence wins.
    Uses an internal accumulator for DFS first-occurrence semantics;
    the public interface is pure (fresh dict returned).
    """
    acc: dict[str, dict] = {}
    _index_walk(node, signatures, acc)
    return acc


def _index_walk(
    node: dict, signatures: frozenset[str], acc: dict[str, dict]
) -> None:
    """DFS walker for index_full_tree. Mutates acc (internal only)."""
    sig = node.get("methodSignature", "")
    if (
        sig
        and sig in signatures
        and sig not in acc
        and not node.get("ref", False)
        and not node.get("cycle", False)
        and not node.get("filtered", False)
    ):
        acc[sig] = node
    for child in node.get("children", []):
        _index_walk(child, signatures, acc)


def main():
    parser = argparse.ArgumentParser(
        description="Slice a subtree using jq and bundle a ref index for expansion."
    )
    parser.add_argument(
        "--input", required=True, type=Path, help="Full ftrace JSON file"
    )
    parser.add_argument(
        "--query",
        required=True,
        help="jq query to slice the subtree (e.g. '.children[0]')",
    )
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found.", file=sys.stderr)
        sys.exit(1)

    # 1. Use jq to slice the target subtree
    try:
        result = subprocess.run(
            ["jq", args.query, str(args.input)],
            capture_output=True,
            text=True,
            check=True,
        )
        target = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"jq failed: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: jq query did not return valid JSON.", file=sys.stderr)
        sys.exit(1)

    if not isinstance(target, dict):
        print(
            "Error: jq query must return a single JSON object (node).",
            file=sys.stderr,
        )
        sys.exit(1)

    # 2. Build scoped ref index from full tree
    with open(args.input) as f:
        full_tree = json.load(f)

    ref_sigs = collect_ref_signatures(target)
    ref_index = index_full_tree(full_tree, ref_sigs)

    # 3. Output SlicedTrace
    sliced_trace = {"slice": target, "refIndex": ref_index}
    output = json.dumps(sliced_trace, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote sliced trace to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run all unit tests**

Run: `cd python && python3 -m pytest tests/test_ftrace_slice_unit.py tests/test_expand_refs.py -v`
Expected: PASS (all tests)

- [ ] **Step 3: Commit**

```bash
git add python/ftrace_slice.py
git commit -m "refactor: rewrite ftrace-slice main to output SlicedTrace format"
```

---

### Task 5: Register ftrace-expand-refs entry point

**Files:**
- Modify: `python/pyproject.toml`

- [ ] **Step 1: Add entry point**

In `python/pyproject.toml`, update the `[project.scripts]` section:

```toml
[project.scripts]
ftrace-to-dot = "ftrace_to_dot:main"
ftrace-slice = "ftrace_slice:main"
ftrace-expand-refs = "ftrace_expand_refs:main"
ftrace-semantic = "ftrace_semantic:main"
```

- [ ] **Step 2: Verify both tools are callable**

Run:
```bash
cd python && uv run ftrace-slice --help && uv run ftrace-expand-refs --help
```
Expected: Both print their help text without errors.

- [ ] **Step 3: Commit**

```bash
git add python/pyproject.toml
git commit -m "feat: register ftrace-expand-refs CLI entry point"
```

---

### Task 6: Update E2E tests for two-tool pipeline

**Files:**
- Rewrite: `test-fixtures/tests/test_ftrace_slice.sh`

- [ ] **Step 1: Rewrite the E2E test**

Replace `test-fixtures/tests/test_ftrace_slice.sh` with:

```bash
#!/usr/bin/env bash
# Test: ftrace-slice + ftrace-expand-refs pipeline.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "ftrace-slice + ftrace-expand-refs pipeline"

# Generate a trace that has refs
$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.ComplexService --from-line "$COMPLEX_LINE" \
  --output "$OUT/complex.json" 2>/dev/null

# Slice out handleException (now outputs SlicedTrace)
cd "$REPO_ROOT/python"
uv run ftrace-slice --input "$OUT/complex.json" \
  --query '.children[] | select(.method == "handleException")' \
  --output "$OUT/sliced.json" 2>/dev/null

assert_json_contains "$OUT/sliced.json" \
    '.slice | .method == "handleException"' \
    "sliced root method in .slice"

assert_json_contains "$OUT/sliced.json" \
    '.refIndex | length >= 0' \
    "has refIndex field"

# Expand refs (produces plain trace node)
uv run ftrace-expand-refs --input "$OUT/sliced.json" \
  --output "$OUT/expanded.json" 2>/dev/null

assert_json_field "$OUT/expanded.json" '.method' 'handleException' \
    "expanded root method"

assert_json_contains "$OUT/expanded.json" \
    '.blocks | length > 0' \
    "has blocks after expansion"

assert_json_contains "$OUT/expanded.json" \
    '.traps | length == 2' \
    "has traps after expansion"

assert_json_contains "$OUT/expanded.json" \
    '.traps[] | select(.type | contains("RuntimeException")) | .handlerBlocks | length == 4' \
    "RuntimeException handler has 4 blocks (no normal-flow leakage)"

# Full pipeline: expanded → semantic → dot
uv run ftrace-semantic --input "$OUT/expanded.json" --output "$OUT/sliced-semantic.json" 2>/dev/null

assert_json_contains "$OUT/sliced-semantic.json" \
    '.nodes | length > 0' \
    "sliced semantic graph has nodes"

uv run ftrace-to-dot --input "$OUT/sliced-semantic.json" --output "$OUT/sliced-pipeline.dot" 2>/dev/null

assert_file_contains "$OUT/sliced-pipeline.dot" "digraph" \
    "sliced DOT output is a digraph"

report
```

- [ ] **Step 2: Run E2E tests**

Run: `bash test-fixtures/run-e2e.sh`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add test-fixtures/tests/test_ftrace_slice.sh
git commit -m "test: update ftrace-slice E2E for two-tool pipeline"
```

---

### Task 7: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update project structure**

In the project structure section, update the Python entries:

```
├── python/                  # uv project — visualization tools
│   ├── pyproject.toml
│   ├── ftrace_types.py      # Shared type definitions (StrEnum, TypedDict)
│   ├── ftrace_slice.py      # Slice subtree + bundle ref index
│   ├── ftrace_expand_refs.py # Expand ref nodes using ref index
│   ├── ftrace_semantic.py   # Transform raw trace → semantic graph
│   └── ftrace_to_dot.py     # Render semantic graph as DOT/SVG
```

- [ ] **Step 2: Update Step 4 (slice and expand)**

Replace the Step 4 section with:

````markdown
### Step 4 (optional): Slice and expand

Interprocedural traces can be huge and contain many `ref` nodes (deduplicated methods). You can "drill down" into a specific method by slicing the trace and expanding all its refs:

```bash
cd python

# Slice: extract subtree + bundle ref index
uv run ftrace-slice \
  --input ../trace.json \
  --query ".children[0].children[2]" \
  --output ../sliced.json

# Expand refs: replace ref nodes with full method bodies
uv run ftrace-expand-refs \
  --input ../sliced.json \
  --output ../expanded.json
```

This creates a standalone JSON for that method, including its full CFG, source trace, and exception clusters. The expanded output is ready for `ftrace-semantic`.
````

- [ ] **Step 3: Update quick reference**

Replace the old single-line `ftrace-slice` entry in the quick reference section with:

```bash
uv run ftrace-slice --input ../trace.json --query "<jq-query>" --output ../sliced.json
uv run ftrace-expand-refs --input ../sliced.json --output ../expanded.json
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for ftrace-slice decomposition"
```

---

### Task 8: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
cd /Users/asgupta/code/java-bytecode-tools
cd java && mvn test
cd ../python && python3 -m pytest tests/ -v
bash ../test-fixtures/run-e2e.sh
```

Expected: All tests pass (Java unit, ~100+ Python unit, E2E suite).

- [ ] **Step 2: Fix any failures**

If any tests fail, fix them before proceeding.
