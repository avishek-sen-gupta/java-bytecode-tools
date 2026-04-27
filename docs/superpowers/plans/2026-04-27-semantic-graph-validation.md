# Semantic Graph Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a validation module that checks structural invariants on finished `MethodSemanticCFG` trees, and fix the branch edge dedup bug that collapses T/F edges.

**Architecture:** A new `ftrace_validate.py` module with pure check functions composed into `validate_method` and `validate_tree`. Types (`ViolationKind`, `Violation`) live in `ftrace_types.py`. The dedup fix is a targeted change in `_build_inter_block_edges`. The module doubles as a UNIX pipeline tool (`ftrace-validate`).

**Tech Stack:** Python 3.13+, TypedDict, StrEnum, pytest, reduce/comprehensions (FP style)

---

### Task 1: Fix branch edge dedup bug

**Files:**
- Modify: `python/ftrace_semantic.py:504-514` (the `fold_edge` dedup branch)
- Test: `python/tests/test_build_semantic_graph.py` (add to `TestBuildEdges`)

- [ ] **Step 1: Write the failing test**

In `python/tests/test_build_semantic_graph.py`, add to `class TestBuildEdges`:

```python
def test_branch_both_targets_same_keeps_both_labels(self):
    """When T and F both point to the same target, keep both labeled edges."""
    from ftrace_semantic import _build_edges

    result = _build_edges(
        raw_edges=[
            {"fromBlock": "B0", "toBlock": "B1", "label": "T"},
            {"fromBlock": "B0", "toBlock": "B1", "label": "F"},
        ],
        block_first={"B0": "n0", "B1": "n1"},
        block_last={"B0": "n0", "B1": "n1"},
        bid_to_nids={"B0": ["n0"], "B1": ["n1"]},
        block_aliases={},
    )
    branch_edges = [e for e in result["edges"] if "branch" in e]
    assert len(branch_edges) == 2
    labels = {e["branch"] for e in branch_edges}
    assert labels == {"T", "F"}
    # Both edges point to the same target
    assert all(e["to"] == "n1" for e in branch_edges)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd python && uv run pytest tests/test_build_semantic_graph.py::TestBuildEdges::test_branch_both_targets_same_keeps_both_labels -v`
Expected: FAIL — current code replaces both labeled edges with a single unlabeled edge.

- [ ] **Step 3: Fix the dedup logic**

In `python/ftrace_semantic.py`, replace the dedup branch inside `fold_edge` (lines 504-515). The current code:

```python
if key in emitted:
    prev_label = emitted[key]
    # T and F converge to same target → branch is a no-op.
    # Replace the labeled edge with an unlabeled one.
    if label and prev_label and label != prev_label:
        unlabeled: SemanticEdge = {"from": tail_nid, "to": succ_nid}
        new_edges: list[SemanticEdge] = [
            (unlabeled if e["from"] == tail_nid and e["to"] == succ_nid else e)
            for e in edges
        ]
        return (new_edges, {**emitted, key: ""})
    return (edges, emitted)
```

Replace with:

```python
if key in emitted:
    prev_label = emitted[key]
    # Allow T and F edges to same target (branch with converging paths)
    if label and prev_label and label != prev_label:
        return (
            [
                *edges,
                {"from": tail_nid, "to": succ_nid, "branch": BranchLabel(label)},
            ],
            {**emitted, key: label},
        )
    return (edges, emitted)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd python && uv run pytest tests/test_build_semantic_graph.py::TestBuildEdges -v`
Expected: All edge tests PASS, including the new one.

- [ ] **Step 5: Run full test suite**

Run: `cd python && uv run pytest`
Expected: All tests pass. Some existing tests may need updating if they assumed the collapsing behavior — check and fix.

- [ ] **Step 6: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_build_semantic_graph.py
git commit -m "fix: keep both T/F edges when branch targets converge"
```

---

### Task 2: Add Violation types to ftrace_types.py

**Files:**
- Modify: `python/ftrace_types.py` (append after `short_class`)

- [ ] **Step 1: Add types**

Append to `python/ftrace_types.py`:

```python
class ViolationKind(StrEnum):
    """Kinds of semantic graph validation violations."""

    DUPLICATE_NODE_ID = "duplicate_node_id"
    DANGLING_EDGE_REF = "dangling_edge_ref"
    DANGLING_CLUSTER_REF = "dangling_cluster_ref"
    INVALID_ENTRY_NODE = "invalid_entry_node"
    BRANCH_EDGE_VIOLATION = "branch_edge_violation"
    NON_BRANCH_EDGE_VIOLATION = "non_branch_edge_violation"
    LEAF_HAS_GRAPH_FIELDS = "leaf_has_graph_fields"
    NO_INCOMING_EDGE = "no_incoming_edge"


class Violation(TypedDict):
    """A structural invariant violation in a semantic graph."""

    kind: ViolationKind
    node_id: str
    method: str
    message: str
```

- [ ] **Step 2: Run pyright**

Run: `cd python && uv run pyright ftrace_types.py`
Expected: No new errors.

- [ ] **Step 3: Commit**

```bash
git add python/ftrace_types.py
git commit -m "feat: add ViolationKind and Violation types"
```

---

### Task 3: Implement validation checks — unique IDs, edge refs, cluster refs, entry node

**Files:**
- Create: `python/ftrace_validate.py`
- Create: `python/tests/test_validate.py`

- [ ] **Step 1: Write failing tests for structural reference checks**

Create `python/tests/test_validate.py`:

```python
"""Tests for semantic graph validation."""

from ftrace_types import (
    NodeKind,
    ViolationKind,
)


def _make_method(
    nodes=(),
    edges=(),
    clusters=(),
    exception_edges=(),
    entry_node_id="",
    cls="com.example.Svc",
    method="handle",
):
    """Build a minimal MethodSemanticCFG for validation testing."""
    result = {
        "class": cls,
        "method": method,
        "methodSignature": f"<{cls}: void {method}()>",
        "nodes": list(nodes),
        "edges": list(edges),
        "clusters": list(clusters),
        "exceptionEdges": list(exception_edges),
        "children": [],
    }
    if entry_node_id:
        result["entryNodeId"] = entry_node_id
    return result


def _node(nid, kind=NodeKind.PLAIN):
    return {"id": nid, "lines": [1], "kind": kind, "label": ["L1"]}


class TestCheckUniqueIds:
    def test_no_duplicates_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(nodes=[_node("n0"), _node("n1")], entry_node_id="n0")
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.DUPLICATE_NODE_ID] == []

    def test_duplicate_ids_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(nodes=[_node("n0"), _node("n0")], entry_node_id="n0")
        violations = [v for v in validate_method(m) if v["kind"] == ViolationKind.DUPLICATE_NODE_ID]
        assert len(violations) == 1
        assert violations[0]["node_id"] == "n0"


class TestCheckEdgeRefs:
    def test_valid_edges_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0"), _node("n1")],
            edges=[{"from": "n0", "to": "n1"}],
            entry_node_id="n0",
        )
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.DANGLING_EDGE_REF] == []

    def test_dangling_from_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0")],
            edges=[{"from": "n99", "to": "n0"}],
            entry_node_id="n0",
        )
        violations = [v for v in validate_method(m) if v["kind"] == ViolationKind.DANGLING_EDGE_REF]
        assert len(violations) == 1
        assert "n99" in violations[0]["message"]

    def test_dangling_to_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0")],
            edges=[{"from": "n0", "to": "n99"}],
            entry_node_id="n0",
        )
        violations = [v for v in validate_method(m) if v["kind"] == ViolationKind.DANGLING_EDGE_REF]
        assert len(violations) == 1
        assert "n99" in violations[0]["message"]


class TestCheckClusterRefs:
    def test_valid_cluster_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0")],
            clusters=[{"trapType": "Exception", "role": "try", "nodeIds": ["n0"]}],
            entry_node_id="n0",
        )
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.DANGLING_CLUSTER_REF] == []

    def test_dangling_cluster_ref_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0")],
            clusters=[{"trapType": "Exception", "role": "try", "nodeIds": ["n0", "n99"]}],
            entry_node_id="n0",
        )
        violations = [v for v in validate_method(m) if v["kind"] == ViolationKind.DANGLING_CLUSTER_REF]
        assert len(violations) == 1
        assert "n99" in violations[0]["message"]


class TestCheckEntryNode:
    def test_valid_entry_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(nodes=[_node("n0")], entry_node_id="n0")
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.INVALID_ENTRY_NODE] == []

    def test_invalid_entry_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(nodes=[_node("n0")], entry_node_id="n99")
        violations = [v for v in validate_method(m) if v["kind"] == ViolationKind.INVALID_ENTRY_NODE]
        assert len(violations) == 1
        assert "n99" in violations[0]["message"]

    def test_no_entry_no_nodes_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(nodes=[], entry_node_id="")
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.INVALID_ENTRY_NODE] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_validate.py -v`
Expected: FAIL — `ftrace_validate` module does not exist yet.

- [ ] **Step 3: Implement check functions and validate_method**

Create `python/ftrace_validate.py`:

```python
"""Validate structural invariants of a MethodSemanticCFG tree.

Pure validation functions that inspect the finished semantic graph.
No knowledge of how the graph was constructed.
"""

from collections import Counter
from functools import reduce

from ftrace_types import (
    ExceptionEdge,
    MethodSemanticCFG,
    NodeKind,
    SemanticCluster,
    SemanticEdge,
    SemanticNode,
    Violation,
    ViolationKind,
    short_class,
)


def _method_label(method: MethodSemanticCFG) -> str:
    cls = short_class(method.get("class", "?"))
    return f"{cls}.{method.get('method', '?')}"


def _check_unique_ids(
    nodes: list[SemanticNode], method_label: str
) -> list[Violation]:
    counts = Counter(n["id"] for n in nodes)
    return [
        Violation(
            kind=ViolationKind.DUPLICATE_NODE_ID,
            node_id=nid,
            method=method_label,
            message=f"Node ID '{nid}' appears {count} times",
        )
        for nid, count in counts.items()
        if count > 1
    ]


def _check_edge_refs(
    edges: list[SemanticEdge], node_ids: frozenset[str], method_label: str
) -> list[Violation]:
    return [
        Violation(
            kind=ViolationKind.DANGLING_EDGE_REF,
            node_id=ref,
            method=method_label,
            message=f"Edge references non-existent node '{ref}' ({direction})",
        )
        for edge in edges
        for ref, direction in [(edge["from"], "from"), (edge["to"], "to")]
        if ref not in node_ids
    ]


def _check_cluster_refs(
    clusters: list[SemanticCluster], node_ids: frozenset[str], method_label: str
) -> list[Violation]:
    return [
        Violation(
            kind=ViolationKind.DANGLING_CLUSTER_REF,
            node_id=nid,
            method=method_label,
            message=f"Cluster references non-existent node '{nid}'",
        )
        for cluster in clusters
        for nid in cluster.get("nodeIds", [])
        if nid not in node_ids
    ]


def _check_entry_node(
    entry_nid: str, node_ids: frozenset[str], method_label: str
) -> list[Violation]:
    if not entry_nid:
        return []
    if entry_nid not in node_ids:
        return [
            Violation(
                kind=ViolationKind.INVALID_ENTRY_NODE,
                node_id=entry_nid,
                method=method_label,
                message=f"entryNodeId '{entry_nid}' does not exist in nodes",
            )
        ]
    return []


def validate_method(method: MethodSemanticCFG) -> list[Violation]:
    """Validate a single method's semantic graph. Does not recurse into children."""
    # Leaf nodes: check separately
    if method.get("ref", False) or method.get("cycle", False) or method.get("filtered", False):
        return _check_leaf_fields(method)

    nodes = method.get("nodes", [])
    edges = method.get("edges", [])
    clusters = method.get("clusters", [])
    exception_edges = method.get("exceptionEdges", [])
    entry_nid = method.get("entryNodeId", "")
    label = _method_label(method)
    node_ids = frozenset(n["id"] for n in nodes)

    return [
        *_check_unique_ids(nodes, label),
        *_check_edge_refs(edges, node_ids, label),
        *_check_cluster_refs(clusters, node_ids, label),
        *_check_entry_node(entry_nid, node_ids, label),
    ]


def validate_tree(root: MethodSemanticCFG) -> list[Violation]:
    """Validate entire tree recursively. Returns all violations."""
    own = validate_method(root)
    child_violations = [
        v
        for child in root.get("children", [])
        for v in validate_tree(child)
    ]
    return [*own, *child_violations]
```

Note: `_check_branch_edges`, `_check_reachability`, and `_check_leaf_fields` are stubs — they will be added in Tasks 4 and 5. `validate_method` currently calls `_check_leaf_fields` for leaf nodes but it doesn't exist yet. Add a temporary stub:

```python
def _check_leaf_fields(method: MethodSemanticCFG) -> list[Violation]:
    return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/test_validate.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_validate.py python/tests/test_validate.py
git commit -m "feat: add validation checks for unique IDs, edge refs, cluster refs, entry node"
```

---

### Task 4: Implement branch edge checks (invariants 5, 6, 7)

**Files:**
- Modify: `python/ftrace_validate.py` (add `_check_branch_edges`, wire into `validate_method`)
- Modify: `python/tests/test_validate.py` (add tests)

- [ ] **Step 1: Write failing tests**

Add to `python/tests/test_validate.py`:

```python
class TestCheckBranchEdges:
    def test_valid_branch_node_returns_empty(self):
        """Branch node with exactly T and F outgoing edges."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.BRANCH), _node("n1"), _node("n2")],
            edges=[
                {"from": "n0", "to": "n1", "branch": "T"},
                {"from": "n0", "to": "n2", "branch": "F"},
            ],
            entry_node_id="n0",
        )
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.BRANCH_EDGE_VIOLATION] == []

    def test_branch_node_missing_label_reported(self):
        """Branch node with only one outgoing edge."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.BRANCH), _node("n1")],
            edges=[{"from": "n0", "to": "n1", "branch": "T"}],
            entry_node_id="n0",
        )
        violations = [v for v in validate_method(m) if v["kind"] == ViolationKind.BRANCH_EDGE_VIOLATION]
        assert len(violations) == 1
        assert "n0" in violations[0]["node_id"]

    def test_branch_node_with_unlabeled_edge_reported(self):
        """Branch node with an unlabeled outgoing edge."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.BRANCH), _node("n1")],
            edges=[{"from": "n0", "to": "n1"}],
            entry_node_id="n0",
        )
        violations = [v for v in validate_method(m) if v["kind"] == ViolationKind.BRANCH_EDGE_VIOLATION]
        assert len(violations) >= 1

    def test_branch_converging_to_same_target_valid(self):
        """Branch node with T and F both pointing to same node is valid."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.BRANCH), _node("n1")],
            edges=[
                {"from": "n0", "to": "n1", "branch": "T"},
                {"from": "n0", "to": "n1", "branch": "F"},
            ],
            entry_node_id="n0",
        )
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.BRANCH_EDGE_VIOLATION] == []

    def test_non_branch_with_labeled_edge_reported(self):
        """Plain node must not have T/F labeled edges."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.PLAIN), _node("n1")],
            edges=[{"from": "n0", "to": "n1", "branch": "T"}],
            entry_node_id="n0",
        )
        violations = [v for v in validate_method(m) if v["kind"] == ViolationKind.NON_BRANCH_EDGE_VIOLATION]
        assert len(violations) >= 1

    def test_non_branch_with_multiple_outgoing_reported(self):
        """Plain node must not have more than one outgoing edge."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0", NodeKind.CALL), _node("n1"), _node("n2")],
            edges=[
                {"from": "n0", "to": "n1"},
                {"from": "n0", "to": "n2"},
            ],
            entry_node_id="n0",
        )
        violations = [v for v in validate_method(m) if v["kind"] == ViolationKind.NON_BRANCH_EDGE_VIOLATION]
        assert len(violations) == 1

    def test_non_branch_with_single_unlabeled_edge_valid(self):
        """Plain node with one unlabeled outgoing edge is valid."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0"), _node("n1")],
            edges=[{"from": "n0", "to": "n1"}],
            entry_node_id="n0",
        )
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.NON_BRANCH_EDGE_VIOLATION] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_validate.py::TestCheckBranchEdges -v`
Expected: FAIL — `_check_branch_edges` not yet wired into `validate_method`.

- [ ] **Step 3: Implement _check_branch_edges**

Add to `python/ftrace_validate.py`, before `validate_method`:

```python
def _check_branch_edges(
    nodes: list[SemanticNode], edges: list[SemanticEdge], method_label: str
) -> list[Violation]:
    """Check invariants 5, 6, 7: branch vs non-branch outgoing edge rules."""
    node_kinds = {n["id"]: NodeKind(n["kind"]) for n in nodes}

    # Build outgoing edges per node
    outgoing: dict[str, list[SemanticEdge]] = reduce(
        lambda acc, e: {**acc, e["from"]: [*acc.get(e["from"], []), e]},
        edges,
        {},
    )

    def _check_one_node(nid: str, kind: NodeKind) -> list[Violation]:
        outs = outgoing.get(nid, [])
        if kind == NodeKind.BRANCH:
            labels = sorted(e.get("branch", "") for e in outs)
            if labels != ["F", "T"]:
                return [
                    Violation(
                        kind=ViolationKind.BRANCH_EDGE_VIOLATION,
                        node_id=nid,
                        method=method_label,
                        message=f"Branch node '{nid}' has outgoing labels {labels}, expected ['F', 'T']",
                    )
                ]
            return []
        # Non-branch node checks
        labeled = [e for e in outs if e.get("branch", "")]
        multi = len(outs) > 1
        violations: list[Violation] = []
        if labeled:
            violations = [
                *violations,
                Violation(
                    kind=ViolationKind.NON_BRANCH_EDGE_VIOLATION,
                    node_id=nid,
                    method=method_label,
                    message=f"Non-branch node '{nid}' ({kind}) has labeled edges: {[e.get('branch') for e in labeled]}",
                ),
            ]
        if multi:
            violations = [
                *violations,
                Violation(
                    kind=ViolationKind.NON_BRANCH_EDGE_VIOLATION,
                    node_id=nid,
                    method=method_label,
                    message=f"Non-branch node '{nid}' ({kind}) has {len(outs)} outgoing edges (max 1)",
                ),
            ]
        return violations

    return [
        v
        for nid, kind in node_kinds.items()
        for v in _check_one_node(nid, kind)
    ]
```

Wire into `validate_method` — add `_check_branch_edges(nodes, edges, label)` to the return list:

```python
    return [
        *_check_unique_ids(nodes, label),
        *_check_edge_refs(edges, node_ids, label),
        *_check_cluster_refs(clusters, node_ids, label),
        *_check_entry_node(entry_nid, node_ids, label),
        *_check_branch_edges(nodes, edges, label),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/test_validate.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_validate.py python/tests/test_validate.py
git commit -m "feat: add branch edge validation checks (invariants 5, 6, 7)"
```

---

### Task 5: Implement reachability and leaf checks (invariants 8, 9)

**Files:**
- Modify: `python/ftrace_validate.py` (add `_check_reachability`, replace `_check_leaf_fields` stub)
- Modify: `python/tests/test_validate.py` (add tests)

- [ ] **Step 1: Write failing tests**

Add to `python/tests/test_validate.py`:

```python
class TestCheckReachability:
    def test_all_reachable_returns_empty(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0"), _node("n1")],
            edges=[{"from": "n0", "to": "n1"}],
            entry_node_id="n0",
        )
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.NO_INCOMING_EDGE] == []

    def test_unreachable_node_reported(self):
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0"), _node("n1"), _node("n2")],
            edges=[{"from": "n0", "to": "n1"}],
            entry_node_id="n0",
        )
        violations = [v for v in validate_method(m) if v["kind"] == ViolationKind.NO_INCOMING_EDGE]
        assert len(violations) == 1
        assert violations[0]["node_id"] == "n2"

    def test_entry_node_exempt(self):
        """Entry node has no incoming edges — that's valid."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0")],
            edges=[],
            entry_node_id="n0",
        )
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.NO_INCOMING_EDGE] == []

    def test_exception_edge_counts_as_incoming(self):
        """A node reached only via an exception edge is reachable."""
        from ftrace_validate import validate_method

        m = _make_method(
            nodes=[_node("n0"), _node("n1")],
            edges=[],
            exception_edges=[
                {"from": "n0", "to": "n1", "trapType": "Exception", "fromCluster": 0, "toCluster": 1}
            ],
            entry_node_id="n0",
        )
        assert [v for v in validate_method(m) if v["kind"] == ViolationKind.NO_INCOMING_EDGE] == []


class TestCheckLeafFields:
    def test_clean_leaf_returns_empty(self):
        from ftrace_validate import validate_method

        leaf = {"class": "Svc", "method": "run", "methodSignature": "sig", "ref": True}
        assert validate_method(leaf) == []

    def test_leaf_with_nodes_reported(self):
        from ftrace_validate import validate_method

        leaf = {
            "class": "Svc",
            "method": "run",
            "methodSignature": "sig",
            "cycle": True,
            "nodes": [_node("n0")],
        }
        violations = [v for v in validate_method(leaf) if v["kind"] == ViolationKind.LEAF_HAS_GRAPH_FIELDS]
        assert len(violations) == 1
        assert "nodes" in violations[0]["message"]

    def test_leaf_with_edges_reported(self):
        from ftrace_validate import validate_method

        leaf = {
            "class": "Svc",
            "method": "run",
            "methodSignature": "sig",
            "filtered": True,
            "edges": [{"from": "n0", "to": "n1"}],
        }
        violations = [v for v in validate_method(leaf) if v["kind"] == ViolationKind.LEAF_HAS_GRAPH_FIELDS]
        assert len(violations) == 1
        assert "edges" in violations[0]["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_validate.py::TestCheckReachability tests/test_validate.py::TestCheckLeafFields -v`
Expected: FAIL — `_check_reachability` not wired, `_check_leaf_fields` is a stub.

- [ ] **Step 3: Implement _check_reachability and _check_leaf_fields**

Add to `python/ftrace_validate.py`, replacing the `_check_leaf_fields` stub:

```python
def _check_reachability(
    nodes: list[SemanticNode],
    edges: list[SemanticEdge],
    exception_edges: list[ExceptionEdge],
    entry_nid: str,
    method_label: str,
) -> list[Violation]:
    """Check that every node except entry has at least one incoming edge."""
    incoming: frozenset[str] = frozenset(
        [e["to"] for e in edges] + [ee["to"] for ee in exception_edges]
    )
    return [
        Violation(
            kind=ViolationKind.NO_INCOMING_EDGE,
            node_id=n["id"],
            method=method_label,
            message=f"Node '{n['id']}' has no incoming edges and is not the entry node",
        )
        for n in nodes
        if n["id"] != entry_nid and n["id"] not in incoming
    ]


_GRAPH_FIELDS = frozenset({"nodes", "edges", "clusters", "exceptionEdges"})


def _check_leaf_fields(method: MethodSemanticCFG) -> list[Violation]:
    """Check that leaf nodes (ref/cycle/filtered) have no graph fields."""
    label = _method_label(method)
    present = [f for f in _GRAPH_FIELDS if method.get(f)]
    return [
        Violation(
            kind=ViolationKind.LEAF_HAS_GRAPH_FIELDS,
            node_id="",
            method=label,
            message=f"Leaf node has graph fields: {present}",
        )
    ] if present else []
```

Wire `_check_reachability` into `validate_method`:

```python
    return [
        *_check_unique_ids(nodes, label),
        *_check_edge_refs(edges, node_ids, label),
        *_check_cluster_refs(clusters, node_ids, label),
        *_check_entry_node(entry_nid, node_ids, label),
        *_check_branch_edges(nodes, edges, label),
        *_check_reachability(nodes, edges, exception_edges, entry_nid, label),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/test_validate.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_validate.py python/tests/test_validate.py
git commit -m "feat: add reachability and leaf field validation checks"
```

---

### Task 6: Implement validate_tree and integration with transform

**Files:**
- Modify: `python/ftrace_validate.py` (`validate_tree` already exists, just verify)
- Modify: `python/ftrace_semantic.py:777-784` (wire `validate_tree` into `transform`)
- Modify: `python/ftrace_semantic.py:787-820` (log violations in CLI)
- Modify: `python/tests/test_validate.py` (add tree-level test)
- Modify: `python/tests/test_build_semantic_graph.py` (update `TestTransform`)

- [ ] **Step 1: Write failing test for validate_tree**

Add to `python/tests/test_validate.py`:

```python
class TestValidateTree:
    def test_collects_violations_from_children(self):
        from ftrace_validate import validate_tree

        child = _make_method(
            nodes=[_node("n10"), _node("n10")],  # duplicate
            entry_node_id="n10",
            cls="com.example.Child",
            method="run",
        )
        root = _make_method(
            nodes=[_node("n0")],
            entry_node_id="n0",
        )
        root["children"] = [child]

        violations = validate_tree(root)
        child_violations = [v for v in violations if v["method"] == "Child.run"]
        assert len(child_violations) >= 1
        assert child_violations[0]["kind"] == ViolationKind.DUPLICATE_NODE_ID

    def test_clean_tree_returns_empty(self):
        from ftrace_validate import validate_tree

        child = _make_method(
            nodes=[_node("n10")],
            entry_node_id="n10",
            cls="com.example.Child",
            method="run",
        )
        root = _make_method(
            nodes=[_node("n0")],
            edges=[],
            entry_node_id="n0",
        )
        root["children"] = [child]

        assert validate_tree(root) == []

    def test_leaf_children_validated(self):
        from ftrace_validate import validate_tree

        leaf_with_bug = {
            "class": "Svc",
            "method": "bad",
            "methodSignature": "sig",
            "ref": True,
            "nodes": [_node("n0")],
        }
        root = _make_method(
            nodes=[_node("n0")],
            entry_node_id="n0",
        )
        root["children"] = [leaf_with_bug]

        violations = validate_tree(root)
        leaf_violations = [v for v in violations if v["kind"] == ViolationKind.LEAF_HAS_GRAPH_FIELDS]
        assert len(leaf_violations) == 1
```

- [ ] **Step 2: Run tests to verify they pass** (validate_tree already exists from Task 3)

Run: `cd python && uv run pytest tests/test_validate.py::TestValidateTree -v`
Expected: PASS — `validate_tree` was implemented in Task 3.

- [ ] **Step 3: Wire validation into ftrace_semantic.py transform**

In `python/ftrace_semantic.py`, modify `transform`:

```python
def transform(tree: MethodCFG) -> MethodSemanticCFG:
    """Run all four passes on a tree."""
    enriched = reduce(
        lambda acc, fn: fn(acc),
        [merge_stmts_pass, assign_clusters_pass, deduplicate_blocks_pass],
        tree,
    )
    return build_semantic_graph_pass(enriched)
```

Change to:

```python
def transform(tree: MethodCFG) -> tuple[MethodSemanticCFG, list["Violation"]]:
    """Run all four passes on a tree, then validate. Returns (result, violations)."""
    from ftrace_validate import validate_tree

    enriched = reduce(
        lambda acc, fn: fn(acc),
        [merge_stmts_pass, assign_clusters_pass, deduplicate_blocks_pass],
        tree,
    )
    result = build_semantic_graph_pass(enriched)
    violations = validate_tree(result)
    return (result, violations)
```

Add the import at top of file:

```python
from ftrace_types import Violation
```

Wait — `Violation` is already available since `ftrace_types` is imported. But changing `transform`'s return type is a breaking change for the CLI `main()`. Update `main()` in `ftrace_semantic.py`:

```python
    result, violations = transform(tree)
    output = json.dumps(result, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote semantic graph to {args.output}", file=sys.stderr)
    else:
        print(output)

    if violations:
        import logging
        logger = logging.getLogger("ftrace-semantic")
        for v in violations:
            logger.warning("[%s] %s: %s", v["kind"], v["method"], v["message"])
```

- [ ] **Step 4: Update TestTransform tests**

In `python/tests/test_build_semantic_graph.py`, update `TestTransform`:

```python
class TestTransform:
    def test_transform_runs_all_passes(self):
        from ftrace_semantic import transform

        tree = {
            "class": "Svc",
            "method": "run",
            "methodSignature": "<Svc: void run()>",
            "lineStart": 1,
            "lineEnd": 10,
            "sourceLineCount": 10,
            "blocks": [
                {"id": "B0", "stmts": [{"line": 5}]},
                {"id": "B1", "stmts": [{"line": 10, "call": "Foo.bar"}]},
            ],
            "edges": [{"fromBlock": "B0", "toBlock": "B1"}],
            "traps": [],
            "children": [],
        }
        result, violations = transform(tree)

        # Should have semantic fields
        assert "nodes" in result
        assert "edges" in result
        assert "clusters" in result
        assert "exceptionEdges" in result

        # Should not have raw fields
        assert "blocks" not in result
        assert "traps" not in result

        # Clean graph should have no violations
        assert violations == []

    def test_transform_leaf_node(self):
        from ftrace_semantic import transform

        tree = {"class": "Svc", "method": "run", "methodSignature": "sig", "ref": True}
        result, violations = transform(tree)
        assert result.get("ref") is True
        assert "nodes" not in result
        assert violations == []
```

- [ ] **Step 5: Run all tests**

Run: `cd python && uv run pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add python/ftrace_semantic.py python/ftrace_validate.py python/tests/test_validate.py python/tests/test_build_semantic_graph.py
git commit -m "feat: integrate validate_tree into transform pipeline"
```

---

### Task 7: Add ftrace-validate CLI entry point

**Files:**
- Modify: `python/ftrace_validate.py` (add `main()`)
- Modify: `python/pyproject.toml` (add entry point)

- [ ] **Step 1: Add main() to ftrace_validate.py**

Add at the bottom of `python/ftrace_validate.py`:

```python
def main():
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Validate structural invariants of a semantic graph JSON."
    )
    parser.add_argument("--input", type=Path, help="Input semantic JSON file (default: stdin)")
    parser.add_argument("--output", type=Path, help="Output JSON file (default: stdout, pass-through)")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            root = json.load(f)
    else:
        root = json.load(sys.stdin)

    violations = validate_tree(root)

    # Pass-through: emit the JSON unchanged
    output = json.dumps(root, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(output)

    # Report violations to stderr
    if violations:
        print(f"\n{len(violations)} violation(s) found:", file=sys.stderr)
        for v in violations:
            print(f"  [{v['kind']}] {v['method']}: {v['message']}", file=sys.stderr)
        sys.exit(1)
    else:
        print("No violations found.", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Register entry point in pyproject.toml**

In `python/pyproject.toml`, add to `[project.scripts]`:

```toml
ftrace-validate = "ftrace_validate:main"
```

- [ ] **Step 3: Test CLI manually**

Run: `cd python && uv run ftrace-validate --input /tmp/pipeline-out/chk-semantic.json 2>&1 | tail -5`
Expected: Either "No violations found." or a list of violations (the branch convergence nodes n224/n354 should now be fixed from Task 1 — if not, they'll show up here as violations, confirming the validator works).

- [ ] **Step 4: Test pipeline mode**

Run: `cd python && cat /tmp/pipeline-out/chk-semantic.json | uv run ftrace-validate > /dev/null`
Expected: Violations (if any) printed to stderr, JSON passed through to stdout.

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_validate.py python/pyproject.toml
git commit -m "feat: add ftrace-validate CLI entry point with UNIX pipe support"
```

---

### Task 8: End-to-end verification

**Files:** (no new files)

- [ ] **Step 1: Re-run the full pipeline on chkParentConflict**

```bash
cd /Users/asgupta/code/java-bytecode-tools/python
uv run ftrace-semantic --input /tmp/pipeline-out/chk-trace.json --output /tmp/pipeline-out/chk-semantic.json
uv run ftrace-validate --input /tmp/pipeline-out/chk-semantic.json --output /tmp/pipeline-out/chk-validated.json
uv run ftrace-to-dot --input /tmp/pipeline-out/chk-validated.json --output /tmp/pipeline-out/chk-trace.svg
```

Expected: Validation passes (exit 0) or reports real violations that need upstream fixes. SVG renders correctly.

- [ ] **Step 2: Run full test suite**

Run: `cd python && uv run pytest`
Expected: All tests pass.

- [ ] **Step 3: Verify pipeline mode**

```bash
cd /Users/asgupta/code/java-bytecode-tools/python
uv run ftrace-semantic --input /tmp/pipeline-out/chk-trace.json | uv run ftrace-validate | uv run ftrace-to-dot --output /tmp/pipeline-out/chk-piped.svg
```

Expected: SVG rendered, validation status on stderr.
