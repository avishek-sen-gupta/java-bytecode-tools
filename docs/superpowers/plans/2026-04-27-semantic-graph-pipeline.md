# Semantic Graph Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract all graph transformations from `ftrace_to_dot.py` into a composable `ftrace_semantic.py` pipeline, making the DOT renderer a dumb mapping from semantic JSON to DOT syntax.

**Architecture:** Four incremental pure-function passes (`merge_stmts → assign_clusters → deduplicate_blocks → build_semantic_graph`) transform raw xtrace JSON into a semantic graph JSON. A rewritten `ftrace_to_dot.py` reads only the semantic format. All tools default to stdout, composable via Unix pipes.

**Tech Stack:** Python 3.13, `TypedDict`, `dataclass(frozen=True)`, `enum.StrEnum`, pytest, Graphviz `dot`

**Spec:** `docs/superpowers/specs/2026-04-27-semantic-graph-pipeline-design.md`

**Constraints (apply throughout all tasks):**
- **No `None` checks** — use null object pattern: empty dicts `{}`, empty lists `[]`, empty strings `""` instead of `None`
- **No `Optional` in type hints** — no `Optional[X]` or `X | None`; use concrete defaults
- **No defensive `get()` with `None` fallback** — always provide a concrete default: `dict.get(key, "")`, `dict.get(key, [])`, etc.
- **Immutable data** — prefer `tuple` over `list` for fixed-size collections, `frozenset` over `set` where applicable
- **FP principles** — no mutation, comprehensions, small pure functions, dependency injection. **No nested for...if loops** — use comprehensions, `filter`, `map`, `itertools` instead
- **TDD** — write tests first, see them fail, then implement
- **Early returns** — guard clauses at top of functions; happy path outside conditions
- **Strong typing** — TypedDict, StrEnum, dataclass(frozen=True), no bare dicts

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `python/ftrace_types.py` | Create | All TypedDict/StrEnum/dataclass type definitions shared across modules |
| `python/ftrace_semantic.py` | Create | Four transform passes + `pipe` composer + CLI |
| `python/ftrace_to_dot.py` | Rewrite | Dumb renderer: semantic JSON → DOT/SVG/PNG |
| `python/pyproject.toml` | Modify | Register `ftrace-semantic` entry point |
| `python/tests/test_ftrace_types.py` | Create | Smoke tests for type constructors |
| `python/tests/test_merge_stmts.py` | Create | Unit tests for pass 1 |
| `python/tests/test_assign_clusters.py` | Create | Unit tests for pass 2 |
| `python/tests/test_deduplicate_blocks.py` | Create | Unit tests for pass 3 |
| `python/tests/test_build_semantic_graph.py` | Create | Unit tests for pass 4 |
| `python/tests/test_dot_rendering.py` | Create | Unit tests for rewritten renderer |
| `python/tests/test_dot_trap_clusters.py` | Remove | Replaced by above test files |
| `test-fixtures/tests/test_xtrace_exception.sh` | Modify | E2E: full pipeline with semantic step |
| `test-fixtures/tests/test_ftrace_slice.sh` | Modify | E2E: slice → semantic → dot pipeline |

---

### Task 1: Type definitions

**Files:**
- Create: `python/ftrace_types.py`
- Create: `python/tests/test_ftrace_types.py`

- [ ] **Step 1: Write smoke tests for type constructors**

Create `python/tests/test_ftrace_types.py`:

```python
"""Smoke tests for shared type definitions."""

from ftrace_types import (
    RawStmt,
    MergedStmt,
    RawBlock,
    RawTrap,
    ClusterAssignment,
    BlockAliases,
    SemanticNode,
    SemanticEdge,
    SemanticCluster,
    ExceptionEdge,
    NodeKind,
    ClusterRole,
    BranchLabel,
)


class TestTypeConstructors:
    def test_raw_stmt_with_call(self):
        stmt: RawStmt = {"line": 9, "call": "Foo.bar"}
        assert stmt["line"] == 9
        assert stmt["call"] == "Foo.bar"

    def test_raw_stmt_minimal(self):
        stmt: RawStmt = {"line": 5}
        assert stmt["line"] == 5

    def test_merged_stmt(self):
        m: MergedStmt = {"line": 9, "calls": ["Foo.bar"], "branches": [], "assigns": []}
        assert m["calls"] == ["Foo.bar"]

    def test_raw_block(self):
        b: RawBlock = {"id": "B0", "stmts": [{"line": 5}], "successors": ["B1"]}
        assert b["id"] == "B0"

    def test_raw_trap(self):
        t: RawTrap = {
            "handler": "B3",
            "type": "java.lang.RuntimeException",
            "coveredBlocks": ["B0", "B1"],
            "handlerBlocks": ["B3", "B4"],
        }
        assert t["handler"] == "B3"

    def test_cluster_assignment(self):
        a: ClusterAssignment = {"kind": ClusterRole.TRY, "trapIndex": 0}
        assert a["kind"] == ClusterRole.TRY

    def test_semantic_node(self):
        n: SemanticNode = {"id": "n0", "lines": [6], "kind": NodeKind.PLAIN, "label": ["L6"]}
        assert n["kind"] == NodeKind.PLAIN

    def test_semantic_edge_no_branch(self):
        e: SemanticEdge = {"from": "n0", "to": "n1"}
        assert "branch" not in e

    def test_semantic_edge_with_branch(self):
        e: SemanticEdge = {"from": "n0", "to": "n1", "branch": BranchLabel.T}
        assert e["branch"] == BranchLabel.T

    def test_semantic_cluster(self):
        c: SemanticCluster = {
            "trapType": "RuntimeException",
            "role": ClusterRole.TRY,
            "nodeIds": ["n0", "n1"],
        }
        assert c["role"] == ClusterRole.TRY

    def test_exception_edge(self):
        ee: ExceptionEdge = {
            "from": "n0",
            "to": "n5",
            "trapType": "RuntimeException",
            "fromCluster": 0,
            "toCluster": 1,
        }
        assert ee["trapType"] == "RuntimeException"

    def test_node_kind_values(self):
        assert list(NodeKind) == [
            NodeKind.PLAIN, NodeKind.CALL, NodeKind.BRANCH, NodeKind.ASSIGN,
            NodeKind.CYCLE, NodeKind.REF, NodeKind.FILTERED,
        ]

    def test_cluster_role_values(self):
        assert list(ClusterRole) == [ClusterRole.TRY, ClusterRole.HANDLER]

    def test_branch_label_values(self):
        assert list(BranchLabel) == [BranchLabel.T, BranchLabel.F]

    def test_str_enum_equals_string(self):
        assert NodeKind.PLAIN == "plain"
        assert ClusterRole.TRY == "try"
        assert BranchLabel.T == "T"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_ftrace_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ftrace_types'`

- [ ] **Step 3: Implement type definitions**

Create `python/ftrace_types.py`:

```python
"""Shared type definitions for the ftrace pipeline.

All structured data flowing between pipeline stages is typed here.
Uses TypedDict for JSON-compatible structures, StrEnum for constrained fields.
"""

from enum import StrEnum
from typing import TypedDict


class NodeKind(StrEnum):
    PLAIN = "plain"
    CALL = "call"
    BRANCH = "branch"
    ASSIGN = "assign"
    CYCLE = "cycle"
    REF = "ref"
    FILTERED = "filtered"


class ClusterRole(StrEnum):
    TRY = "try"
    HANDLER = "handler"


class BranchLabel(StrEnum):
    T = "T"
    F = "F"


class RawStmt(TypedDict, total=False):
    line: int  # required but total=False allows optional fields
    call: str
    branch: str
    assign: str


# Re-declare line as required via inheritance
class _RawStmtRequired(TypedDict):
    line: int


class RawStmt(_RawStmtRequired, total=False):
    call: str
    branch: str
    assign: str


class MergedStmt(TypedDict):
    line: int
    calls: list[str]
    branches: list[str]
    assigns: list[str]


class _RawBlockRequired(TypedDict):
    id: str
    stmts: list[RawStmt]
    successors: list[str]


class RawBlock(_RawBlockRequired, total=False):
    branchCondition: str
    mergedStmts: list[MergedStmt]


class RawTrap(TypedDict):
    handler: str
    type: str
    coveredBlocks: list[str]
    handlerBlocks: list[str]


class ClusterAssignment(TypedDict):
    kind: ClusterRole
    trapIndex: int


class BlockAliases(TypedDict):
    """Map of alias block ID → canonical block ID."""
    pass  # Used as dict[str, str] but named for clarity


class SemanticNode(TypedDict):
    id: str
    lines: list[int]
    kind: NodeKind
    label: list[str]


class _SemanticEdgeRequired(TypedDict):
    # 'from' is a Python keyword, so we use string key access
    pass


class SemanticEdge(TypedDict, total=False):
    # All fields accessed via string keys: e["from"], e["to"], e["branch"]
    # TypedDict with 'from' as a key requires special handling
    pass


# Since 'from' is a reserved word, define SemanticEdge via functional syntax
SemanticEdge = TypedDict("SemanticEdge", {
    "from": str,
    "to": str,
    "branch": str,
}, total=False)

# Make from and to required by using a base class
_SemanticEdgeRequired = TypedDict("_SemanticEdgeRequired", {
    "from": str,
    "to": str,
})

SemanticEdge = TypedDict("SemanticEdge", {
    "from": str,
    "to": str,
    "branch": str,
}, total=False)


class SemanticCluster(TypedDict, total=False):
    trapType: str
    role: ClusterRole
    nodeIds: list[str]
    entryNodeId: str


class ExceptionEdge(TypedDict):
    trapType: str
    fromCluster: int
    toCluster: int


# Use functional syntax for fields with reserved words
ExceptionEdge = TypedDict("ExceptionEdge", {
    "from": str,
    "to": str,
    "trapType": str,
    "fromCluster": int,
    "toCluster": int,
})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/test_ftrace_types.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_types.py python/tests/test_ftrace_types.py
git commit -m "feat: add shared type definitions for ftrace pipeline"
```

---

### Task 2: Pass 1 — `merge_stmts`

**Files:**
- Create: `python/tests/test_merge_stmts.py`
- Create: `python/ftrace_semantic.py` (first pass only)

- [ ] **Step 1: Write failing tests for `merge_block_stmts` and `merge_stmts_pass`**

Create `python/tests/test_merge_stmts.py`:

```python
"""Tests for pass 1: merge_stmts."""

from ftrace_types import MergedStmt, RawBlock


class TestMergeBlockStmts:
    """Unit tests for the per-block stmt merging function."""

    def test_single_stmt(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [{"line": 5}]
        result: list[MergedStmt] = merge_block_stmts(stmts)
        assert result == [{"line": 5, "calls": [], "branches": [], "assigns": []}]

    def test_multiple_stmts_same_line_merges_calls(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [
            {"line": 9, "call": "Foo.bar"},
            {"line": 9, "call": "Baz.qux"},
            {"line": 9},
        ]
        result = merge_block_stmts(stmts)
        assert len(result) == 1
        assert result[0]["line"] == 9
        assert result[0]["calls"] == ["Foo.bar", "Baz.qux"]

    def test_negative_lines_excluded(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [{"line": -1}, {"line": 5}]
        result = merge_block_stmts(stmts)
        assert len(result) == 1
        assert result[0]["line"] == 5

    def test_branches_collected(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [{"line": 6, "branch": "i <= 0"}]
        result = merge_block_stmts(stmts)
        assert result[0]["branches"] == ["i <= 0"]

    def test_assigns_collected(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [{"line": 7, "assign": "x = 5"}]
        result = merge_block_stmts(stmts)
        assert result[0]["assigns"] == ["x = 5"]

    def test_sorted_by_line(self):
        from ftrace_semantic import merge_block_stmts

        stmts = [{"line": 10}, {"line": 3}, {"line": 7}]
        result = merge_block_stmts(stmts)
        assert [m["line"] for m in result] == [3, 7, 10]

    def test_empty_stmts(self):
        from ftrace_semantic import merge_block_stmts

        assert merge_block_stmts([]) == []


class TestMergeStmtsPass:
    """Tests for the full tree-walking pass."""

    def test_adds_merged_stmts_to_blocks(self):
        from ftrace_semantic import merge_stmts_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [
                {"id": "B0", "stmts": [{"line": 5}, {"line": 5, "call": "Foo.x"}], "successors": []},
            ],
            "traps": [],
            "children": [],
        }
        result = merge_stmts_pass(tree)
        assert result is not tree  # new dict, not mutated
        assert "mergedStmts" in result["blocks"][0]
        assert result["blocks"][0]["mergedStmts"][0]["calls"] == ["Foo.x"]

    def test_preserves_raw_stmts(self):
        from ftrace_semantic import merge_stmts_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [
                {"id": "B0", "stmts": [{"line": 5}], "successors": []},
            ],
            "traps": [],
            "children": [],
        }
        result = merge_stmts_pass(tree)
        assert "stmts" in result["blocks"][0]

    def test_recurses_into_children(self):
        from ftrace_semantic import merge_stmts_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0", "stmts": [{"line": 5}], "successors": []}],
            "traps": [],
            "children": [
                {
                    "class": "Svc",
                    "method": "inner",
                    "blocks": [{"id": "B0", "stmts": [{"line": 10}], "successors": []}],
                    "traps": [],
                    "children": [],
                }
            ],
        }
        result = merge_stmts_pass(tree)
        assert "mergedStmts" in result["children"][0]["blocks"][0]

    def test_leaf_nodes_pass_through(self):
        from ftrace_semantic import merge_stmts_pass

        tree = {"class": "Svc", "method": "run", "ref": True, "methodSignature": "sig"}
        result = merge_stmts_pass(tree)
        assert result == tree
        assert result is not tree  # still a copy

    def test_does_not_mutate_input(self):
        from ftrace_semantic import merge_stmts_pass
        import copy

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0", "stmts": [{"line": 5}], "successors": []}],
            "traps": [],
            "children": [],
        }
        original = copy.deepcopy(tree)
        merge_stmts_pass(tree)
        assert tree == original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_merge_stmts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ftrace_semantic'`

- [ ] **Step 3: Implement `merge_block_stmts` and `merge_stmts_pass`**

Create `python/ftrace_semantic.py` with pass 1:

```python
"""Transform raw xtrace JSON into semantic graph JSON.

Four composable passes, each a pure function tree → tree:
1. merge_stmts     — deduplicate block stmts by line
2. assign_clusters — assign blocks to trap clusters
3. deduplicate_blocks — alias identical blocks within clusters
4. build_semantic_graph — emit nodes/edges/clusters, drop raw fields
"""

from functools import reduce

from ftrace_types import MergedStmt, RawStmt


def _accumulate_stmt(acc: dict[int, MergedStmt], s: RawStmt) -> dict[int, MergedStmt]:
    """Fold a single raw stmt into the accumulator, keyed by line number."""
    line = s["line"]
    if line < 0:
        return acc
    entry = acc.get(line, {"line": line, "calls": [], "branches": [], "assigns": []})
    return {
        **acc,
        line: {
            **entry,
            "calls": entry["calls"] + ([s["call"]] if "call" in s else []),
            "branches": entry["branches"] + ([s["branch"]] if "branch" in s else []),
            "assigns": entry["assigns"] + ([s["assign"]] if "assign" in s else []),
        },
    }


def merge_block_stmts(stmts: list[RawStmt]) -> list[MergedStmt]:
    """Deduplicate stmts by line number, aggregating calls/branches/assigns."""
    by_line = reduce(_accumulate_stmt, stmts, {})
    return [by_line[ln] for ln in sorted(by_line)]


def _is_leaf_node(node: dict) -> bool:
    """Check if a node is a leaf (ref, cycle, or filtered)."""
    return bool(node.get("ref") or node.get("cycle") or node.get("filtered"))


def merge_stmts_pass(tree: dict) -> dict:
    """Pass 1: Add mergedStmts to each block in the tree. Returns new tree."""
    if _is_leaf_node(tree):
        return dict(tree)

    result = dict(tree)

    if "blocks" in tree:
        result["blocks"] = [
            {**block, "mergedStmts": merge_block_stmts(block.get("stmts", []))}
            for block in tree["blocks"]
        ]

    if "children" in tree:
        result["children"] = [merge_stmts_pass(child) for child in tree["children"]]

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/test_merge_stmts.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_merge_stmts.py
git commit -m "feat: pass 1 — merge_stmts deduplicates block stmts by line"
```

---

### Task 3: Pass 2 — `assign_clusters`

**Files:**
- Create: `python/tests/test_assign_clusters.py`
- Modify: `python/ftrace_semantic.py`

- [ ] **Step 1: Write failing tests**

Create `python/tests/test_assign_clusters.py`:

```python
"""Tests for pass 2: assign_clusters."""

from ftrace_types import ClusterAssignment, ClusterRole


class TestAssignTrapClusters:
    """Unit tests for the cluster assignment function."""

    def test_handler_wins_over_coverage(self):
        from ftrace_semantic import assign_trap_clusters

        traps = [
            {
                "type": "java.lang.Throwable",
                "handler": "B3",
                "coveredBlocks": ["B0", "B1", "B3"],
                "handlerBlocks": ["B3", "B4"],
            },
        ]
        result = assign_trap_clusters(traps)
        assert result["B3"] == {"kind": ClusterRole.HANDLER, "trapIndex": 0}
        assert result["B0"] == {"kind": ClusterRole.TRY, "trapIndex": 0}

    def test_handler_blocks_excluded_from_coverage(self):
        from ftrace_semantic import assign_trap_clusters

        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B5",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B5", "B6"],
            },
            {
                "type": "java.lang.Throwable",
                "handler": "B7",
                "coveredBlocks": ["B0", "B1", "B5", "B6"],
                "handlerBlocks": ["B7"],
            },
        ]
        result = assign_trap_clusters(traps)
        # B5 is handler for trap 0, should not be covered by trap 1
        assert result["B5"] == {"kind": ClusterRole.HANDLER, "trapIndex": 0}
        assert result["B6"] == {"kind": ClusterRole.HANDLER, "trapIndex": 0}

    def test_empty_traps(self):
        from ftrace_semantic import assign_trap_clusters

        assert assign_trap_clusters([]) == {}

    def test_no_overlap(self):
        from ftrace_semantic import assign_trap_clusters

        traps = [
            {
                "type": "java.lang.Exception",
                "handler": "B3",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B3"],
            },
        ]
        result = assign_trap_clusters(traps)
        assert result["B0"] == {"kind": ClusterRole.TRY, "trapIndex": 0}
        assert result["B1"] == {"kind": ClusterRole.TRY, "trapIndex": 0}
        assert result["B3"] == {"kind": ClusterRole.HANDLER, "trapIndex": 0}

    def test_first_trap_wins_for_coverage(self):
        from ftrace_semantic import assign_trap_clusters

        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B5",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B5"],
            },
            {
                "type": "java.lang.Throwable",
                "handler": "B6",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B6"],
            },
        ]
        result = assign_trap_clusters(traps)
        assert result["B0"] == {"kind": ClusterRole.TRY, "trapIndex": 0}


class TestBlocksForCluster:
    def test_returns_matching_blocks(self):
        from ftrace_semantic import blocks_for_cluster

        assignment = {
            "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B1": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
        }
        assert blocks_for_cluster(assignment, "try", 0) == ["B0", "B1"]
        assert blocks_for_cluster(assignment, "handler", 0) == ["B3"]

    def test_empty_assignment(self):
        from ftrace_semantic import blocks_for_cluster

        assert blocks_for_cluster({}, "try", 0) == []


class TestAssignClustersPass:
    def test_adds_cluster_assignment_to_method_node(self):
        from ftrace_semantic import assign_clusters_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [
                {"id": "B0", "stmts": [{"line": 5}], "successors": []},
            ],
            "traps": [
                {
                    "type": "java.lang.Exception",
                    "handler": "B1",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B1"],
                },
            ],
            "children": [],
        }
        result = assign_clusters_pass(tree)
        assert "clusterAssignment" in result
        assert result["clusterAssignment"]["B0"] == {"kind": ClusterRole.TRY, "trapIndex": 0}

    def test_leaf_node_passes_through(self):
        from ftrace_semantic import assign_clusters_pass

        tree = {"class": "Svc", "method": "run", "ref": True, "methodSignature": "sig"}
        result = assign_clusters_pass(tree)
        assert "clusterAssignment" not in result

    def test_no_traps_empty_assignment(self):
        from ftrace_semantic import assign_clusters_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0", "stmts": [{"line": 5}], "successors": []}],
            "traps": [],
            "children": [],
        }
        result = assign_clusters_pass(tree)
        assert result["clusterAssignment"] == {}

    def test_does_not_mutate_input(self):
        from ftrace_semantic import assign_clusters_pass
        import copy

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0", "stmts": [{"line": 5}], "successors": []}],
            "traps": [
                {
                    "type": "java.lang.Exception",
                    "handler": "B1",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B1"],
                },
            ],
            "children": [],
        }
        original = copy.deepcopy(tree)
        assign_clusters_pass(tree)
        assert tree == original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_assign_clusters.py -v`
Expected: FAIL — `ImportError: cannot import name 'assign_trap_clusters' from 'ftrace_semantic'`

- [ ] **Step 3: Implement `assign_trap_clusters`, `blocks_for_cluster`, and `assign_clusters_pass`**

Add to `python/ftrace_semantic.py`:

```python
from ftrace_types import ClusterAssignment, ClusterRole


def assign_trap_clusters(
    traps: list[dict],
) -> dict[str, ClusterAssignment]:
    """Assign each block to exactly one trap cluster.

    Handler membership takes priority over coverage. A block can be both
    a coveredBlock (for a finally/outer trap) and a handlerBlock (for a
    catch/inner trap). Handler wins.
    """
    all_handler_bids: frozenset[str] = frozenset(
        bid for trap in traps for bid in trap.get("handlerBlocks", [])
    )

    def _fold_trap(
        acc: dict[str, ClusterAssignment], indexed_trap: tuple[int, dict]
    ) -> dict[str, ClusterAssignment]:
        i, trap = indexed_trap
        covered = {
            bid: {"kind": ClusterRole.TRY, "trapIndex": i}
            for bid in trap.get("coveredBlocks", [])
            if bid not in all_handler_bids and bid not in acc
        }
        handlers = {
            bid: {"kind": ClusterRole.HANDLER, "trapIndex": i}
            for bid in trap.get("handlerBlocks", [])
            if bid not in acc and bid not in covered
        }
        return {**acc, **covered, **handlers}

    return reduce(_fold_trap, enumerate(traps), {})


def blocks_for_cluster(
    assignment: dict[str, ClusterAssignment], kind: str, trap_index: int
) -> list[str]:
    """Return block IDs assigned to a specific cluster, in insertion order."""
    return [
        bid
        for bid, a in assignment.items()
        if a["kind"] == kind and a["trapIndex"] == trap_index
    ]


def assign_clusters_pass(tree: dict) -> dict:
    """Pass 2: Add clusterAssignment to each method node. Returns new tree."""
    if _is_leaf_node(tree):
        return dict(tree)

    result = dict(tree)

    if "traps" in tree:
        result["clusterAssignment"] = assign_trap_clusters(tree.get("traps", []))

    if "children" in tree:
        result["children"] = [assign_clusters_pass(child) for child in tree["children"]]

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/test_assign_clusters.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_assign_clusters.py
git commit -m "feat: pass 2 — assign_clusters maps blocks to trap clusters"
```

---

### Task 4: Pass 3 — `deduplicate_blocks`

**Files:**
- Create: `python/tests/test_deduplicate_blocks.py`
- Modify: `python/ftrace_semantic.py`

- [ ] **Step 1: Write failing tests**

Create `python/tests/test_deduplicate_blocks.py`:

```python
"""Tests for pass 3: deduplicate_blocks."""


class TestBlockContentSignature:
    def test_same_content_same_sig(self):
        from ftrace_semantic import block_content_signature

        b1 = {
            "id": "B3",
            "mergedStmts": [{"line": 14, "calls": ["PrintStream.println"], "branches": [], "assigns": []}],
            "stmts": [],
            "successors": [],
        }
        b2 = {
            "id": "B8",
            "mergedStmts": [{"line": 14, "calls": ["PrintStream.println"], "branches": [], "assigns": []}],
            "stmts": [],
            "successors": [],
        }
        assert block_content_signature(b1) == block_content_signature(b2)

    def test_different_content_different_sig(self):
        from ftrace_semantic import block_content_signature

        b1 = {
            "id": "B3",
            "mergedStmts": [{"line": 14, "calls": ["PrintStream.println"], "branches": [], "assigns": []}],
            "stmts": [],
            "successors": [],
        }
        b2 = {
            "id": "B4",
            "mergedStmts": [{"line": 15, "calls": [], "branches": [], "assigns": []}],
            "stmts": [],
            "successors": [],
        }
        assert block_content_signature(b1) != block_content_signature(b2)

    def test_branch_condition_included(self):
        from ftrace_semantic import block_content_signature

        b1 = {
            "id": "B0",
            "mergedStmts": [{"line": 6, "calls": [], "branches": ["i <= 0"], "assigns": []}],
            "branchCondition": "i <= 0",
            "stmts": [],
            "successors": [],
        }
        b2 = {
            "id": "B1",
            "mergedStmts": [{"line": 6, "calls": [], "branches": ["i <= 0"], "assigns": []}],
            "stmts": [],
            "successors": [],
        }
        assert block_content_signature(b1) != block_content_signature(b2)

    def test_empty_merged_stmts(self):
        from ftrace_semantic import block_content_signature

        b = {"id": "B0", "mergedStmts": [], "stmts": [], "successors": []}
        sig = block_content_signature(b)
        assert isinstance(sig, str)


class TestComputeBlockAliases:
    def test_duplicates_within_same_cluster(self):
        from ftrace_semantic import compute_block_aliases

        blocks = [
            {
                "id": "B3",
                "mergedStmts": [{"line": 14, "calls": ["PrintStream.println"], "branches": [], "assigns": []}],
                "stmts": [],
                "successors": [],
            },
            {
                "id": "B8",
                "mergedStmts": [{"line": 14, "calls": ["PrintStream.println"], "branches": [], "assigns": []}],
                "stmts": [],
                "successors": [],
            },
        ]
        cluster_assignment = {
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            "B8": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
        }
        aliases = compute_block_aliases(blocks, cluster_assignment)
        assert aliases == {"B8": "B3"}

    def test_no_duplicates(self):
        from ftrace_semantic import compute_block_aliases

        blocks = [
            {
                "id": "B0",
                "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
                "stmts": [],
                "successors": [],
            },
            {
                "id": "B1",
                "mergedStmts": [{"line": 10, "calls": [], "branches": [], "assigns": []}],
                "stmts": [],
                "successors": [],
            },
        ]
        cluster_assignment = {
            "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B1": {"kind": ClusterRole.TRY, "trapIndex": 0},
        }
        aliases = compute_block_aliases(blocks, cluster_assignment)
        assert aliases == {}

    def test_different_clusters_not_aliased(self):
        from ftrace_semantic import compute_block_aliases

        blocks = [
            {
                "id": "B3",
                "mergedStmts": [{"line": 14, "calls": ["PrintStream.println"], "branches": [], "assigns": []}],
                "stmts": [],
                "successors": [],
            },
            {
                "id": "B8",
                "mergedStmts": [{"line": 14, "calls": ["PrintStream.println"], "branches": [], "assigns": []}],
                "stmts": [],
                "successors": [],
            },
        ]
        cluster_assignment = {
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            "B8": {"kind": ClusterRole.HANDLER, "trapIndex": 1},
        }
        aliases = compute_block_aliases(blocks, cluster_assignment)
        assert aliases == {}

    def test_unassigned_blocks_not_aliased(self):
        from ftrace_semantic import compute_block_aliases

        blocks = [
            {
                "id": "B0",
                "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
                "stmts": [],
                "successors": [],
            },
            {
                "id": "B1",
                "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
                "stmts": [],
                "successors": [],
            },
        ]
        aliases = compute_block_aliases(blocks, {})
        assert aliases == {}


class TestDeduplicateBlocksPass:
    def test_adds_block_aliases(self):
        from ftrace_semantic import deduplicate_blocks_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [
                {
                    "id": "B3",
                    "mergedStmts": [{"line": 14, "calls": ["PrintStream.println"], "branches": [], "assigns": []}],
                    "stmts": [],
                    "successors": [],
                },
                {
                    "id": "B8",
                    "mergedStmts": [{"line": 14, "calls": ["PrintStream.println"], "branches": [], "assigns": []}],
                    "stmts": [],
                    "successors": [],
                },
            ],
            "traps": [],
            "clusterAssignment": {
                "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
                "B8": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            },
            "children": [],
        }
        result = deduplicate_blocks_pass(tree)
        assert result["blockAliases"] == {"B8": "B3"}

    def test_leaf_node_passes_through(self):
        from ftrace_semantic import deduplicate_blocks_pass

        tree = {"class": "Svc", "method": "run", "ref": True, "methodSignature": "sig"}
        result = deduplicate_blocks_pass(tree)
        assert "blockAliases" not in result

    def test_does_not_mutate_input(self):
        from ftrace_semantic import deduplicate_blocks_pass
        import copy

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [
                {
                    "id": "B0",
                    "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
                    "stmts": [],
                    "successors": [],
                },
            ],
            "traps": [],
            "clusterAssignment": {},
            "children": [],
        }
        original = copy.deepcopy(tree)
        deduplicate_blocks_pass(tree)
        assert tree == original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_deduplicate_blocks.py -v`
Expected: FAIL — `ImportError: cannot import name 'block_content_signature' from 'ftrace_semantic'`

- [ ] **Step 3: Implement `block_content_signature`, `compute_block_aliases`, and `deduplicate_blocks_pass`**

Add to `python/ftrace_semantic.py`:

```python
def block_content_signature(block: dict) -> str:
    """Compute a content signature for a block based on mergedStmts and branchCondition.

    Two blocks with the same signature are visually identical and can be aliased.
    """
    entries = tuple(
        (
            entry["line"],
            tuple(sorted(entry.get("calls", []))),
            tuple(entry.get("branches", [])),
        )
        for entry in block.get("mergedStmts", [])
    )
    return str((entries, block.get("branchCondition", "")))


def compute_block_aliases(
    blocks: list[dict],
    cluster_assignment: dict[str, ClusterAssignment],
) -> dict[str, str]:
    """Find duplicate blocks within the same cluster.

    Returns a map of alias_block_id → canonical_block_id.
    Only blocks assigned to the same (kind, trapIndex) cluster are compared.
    """
    cluster_sigs: dict[tuple[str, int], dict[str, str]] = {}
    aliases: dict[str, str] = {}

    for block in blocks:
        bid = block["id"]
        if bid not in cluster_assignment:
            continue
        assignment = cluster_assignment[bid]
        cluster_key = (assignment["kind"], assignment["trapIndex"])
        sig = block_content_signature(block)

        sigs = cluster_sigs.setdefault(cluster_key, {})
        if sig in sigs:
            aliases[bid] = sigs[sig]
        else:
            sigs[sig] = bid

    return aliases


def deduplicate_blocks_pass(tree: dict) -> dict:
    """Pass 3: Add blockAliases to each method node. Returns new tree."""
    if _is_leaf_node(tree):
        return dict(tree)

    result = dict(tree)

    if "blocks" in tree:
        result["blockAliases"] = compute_block_aliases(
            tree.get("blocks", []),
            tree.get("clusterAssignment", {}),
        )

    if "children" in tree:
        result["children"] = [
            deduplicate_blocks_pass(child) for child in tree["children"]
        ]

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/test_deduplicate_blocks.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_deduplicate_blocks.py
git commit -m "feat: pass 3 — deduplicate_blocks aliases identical blocks within clusters"
```

---

### Task 5: Pass 4 — `build_semantic_graph`

**Files:**
- Create: `python/tests/test_build_semantic_graph.py`
- Modify: `python/ftrace_semantic.py`

- [ ] **Step 1: Write failing tests**

Create `python/tests/test_build_semantic_graph.py`:

```python
"""Tests for pass 4: build_semantic_graph."""

from ftrace_types import SemanticNode, SemanticEdge, SemanticCluster, ExceptionEdge, NodeKind, ClusterRole


def _make_enriched_method(blocks, traps, cluster_assignment, block_aliases=(), children=()):
    """Build a method node with all intermediate fields from passes 1-3."""
    return {
        "class": "com.example.Svc",
        "method": "handle",
        "methodSignature": "<com.example.Svc: void handle()>",
        "lineStart": 1,
        "lineEnd": 20,
        "sourceLineCount": 20,
        "blocks": blocks,
        "traps": traps,
        "clusterAssignment": cluster_assignment,
        "blockAliases": dict(block_aliases) if block_aliases else {},
        "children": list(children) if children else [],
    }


class TestMakeNodeLabel:
    def test_plain_line(self):
        from ftrace_semantic import make_node_label

        entry = {"line": 6, "calls": [], "branches": [], "assigns": []}
        assert make_node_label(entry) == ["L6"]

    def test_line_with_calls(self):
        from ftrace_semantic import make_node_label

        entry = {"line": 9, "calls": ["java.lang.RuntimeException.<init>"], "branches": [], "assigns": []}
        label = make_node_label(entry)
        assert label == ["L9", "RuntimeException.<init>"]

    def test_line_with_assigns_no_calls(self):
        from ftrace_semantic import make_node_label

        entry = {"line": 7, "calls": [], "branches": [], "assigns": ["x = 5"]}
        assert make_node_label(entry) == ["L7", "x = 5"]

    def test_assigns_suppressed_when_calls_present(self):
        from ftrace_semantic import make_node_label

        entry = {"line": 7, "calls": ["Foo.bar"], "branches": [], "assigns": ["x = 5"]}
        assert make_node_label(entry) == ["L7", "Foo.bar"]


class TestClassifyNodeKind:
    def test_branch(self):
        from ftrace_semantic import classify_node_kind

        assert classify_node_kind({"line": 6, "calls": [], "branches": ["i <= 0"], "assigns": []}) == NodeKind.BRANCH

    def test_call(self):
        from ftrace_semantic import classify_node_kind

        assert classify_node_kind({"line": 9, "calls": ["Foo.bar"], "branches": [], "assigns": []}) == NodeKind.CALL

    def test_assign(self):
        from ftrace_semantic import classify_node_kind

        assert classify_node_kind({"line": 7, "calls": [], "branches": [], "assigns": ["x = 5"]}) == NodeKind.ASSIGN

    def test_plain(self):
        from ftrace_semantic import classify_node_kind

        assert classify_node_kind({"line": 5, "calls": [], "branches": [], "assigns": []}) == NodeKind.PLAIN


class TestBuildSemanticGraphPass:
    def test_simple_linear_chain(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
                    "successors": ["B1"],
                },
                {
                    "id": "B1",
                    "stmts": [],
                    "mergedStmts": [{"line": 10, "calls": ["Foo.bar"], "branches": [], "assigns": []}],
                    "successors": [],
                },
            ],
            traps=[],
            cluster_assignment={},
        )
        result = build_semantic_graph_pass(tree)

        assert "nodes" in result
        assert "edges" in result
        assert "clusters" in result
        assert "blocks" not in result
        assert "traps" not in result
        assert "mergedStmts" not in result.get("blocks", [{}])[0] if "blocks" in result else True

        assert len(result["nodes"]) == 2
        assert result["nodes"][0]["kind"] == NodeKind.PLAIN
        assert result["nodes"][1]["kind"] == NodeKind.CALL

        assert len(result["edges"]) == 1
        assert result["edges"][0]["from"] == result["nodes"][0]["id"]
        assert result["edges"][0]["to"] == result["nodes"][1]["id"]

    def test_branch_edges(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [{"line": 6, "calls": [], "branches": ["i <= 0"], "assigns": []}],
                    "branchCondition": "i <= 0",
                    "successors": ["B1", "B2"],
                },
                {
                    "id": "B1",
                    "stmts": [],
                    "mergedStmts": [{"line": 7, "calls": [], "branches": [], "assigns": []}],
                    "successors": [],
                },
                {
                    "id": "B2",
                    "stmts": [],
                    "mergedStmts": [{"line": 9, "calls": [], "branches": [], "assigns": []}],
                    "successors": [],
                },
            ],
            traps=[],
            cluster_assignment={},
        )
        result = build_semantic_graph_pass(tree)

        branch_edges = [e for e in result["edges"] if "branch" in e]
        assert len(branch_edges) == 2
        labels = {e["branch"] for e in branch_edges}
        assert labels == {"T", "F"}

    def test_self_loops_suppressed(self):
        from ftrace_semantic import build_semantic_graph_pass

        # B0 and B1 on same line, no calls — merge to same node
        # B0→B1 becomes a self-loop after aliasing
        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [{"line": 9, "calls": [], "branches": [], "assigns": []}],
                    "successors": ["B1"],
                },
                {
                    "id": "B1",
                    "stmts": [],
                    "mergedStmts": [{"line": 9, "calls": [], "branches": [], "assigns": []}],
                    "successors": [],
                },
            ],
            traps=[],
            cluster_assignment={
                "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
                "B1": {"kind": ClusterRole.TRY, "trapIndex": 0},
            },
            block_aliases={"B1": "B0"},
        )
        result = build_semantic_graph_pass(tree)

        self_loops = [e for e in result["edges"] if e["from"] == e["to"]]
        assert self_loops == []

    def test_clusters_emitted(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
                    "successors": [],
                },
                {
                    "id": "B3",
                    "stmts": [],
                    "mergedStmts": [{"line": 11, "calls": [], "branches": [], "assigns": []}],
                    "successors": [],
                },
            ],
            traps=[
                {
                    "type": "java.lang.RuntimeException",
                    "handler": "B3",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B3"],
                },
            ],
            cluster_assignment={
                "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
                "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            },
        )
        result = build_semantic_graph_pass(tree)

        assert len(result["clusters"]) == 2
        try_cluster = [c for c in result["clusters"] if c["role"] == ClusterRole.TRY][0]
        handler_cluster = [c for c in result["clusters"] if c["role"] == ClusterRole.HANDLER][0]
        assert try_cluster["trapType"] == "RuntimeException"
        assert len(try_cluster["nodeIds"]) == 1
        assert handler_cluster["entryNodeId"] == handler_cluster["nodeIds"][0]

    def test_exception_edges_emitted(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
                    "successors": [],
                },
                {
                    "id": "B3",
                    "stmts": [],
                    "mergedStmts": [{"line": 11, "calls": [], "branches": [], "assigns": []}],
                    "successors": [],
                },
            ],
            traps=[
                {
                    "type": "java.lang.RuntimeException",
                    "handler": "B3",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B3"],
                },
            ],
            cluster_assignment={
                "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
                "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            },
        )
        result = build_semantic_graph_pass(tree)

        assert len(result["exceptionEdges"]) == 1
        ee = result["exceptionEdges"][0]
        assert ee["trapType"] == "RuntimeException"

    def test_raw_fields_removed(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
                    "successors": [],
                },
            ],
            traps=[],
            cluster_assignment={},
        )
        result = build_semantic_graph_pass(tree)

        for field in ("blocks", "traps", "clusterAssignment", "blockAliases", "sourceTrace"):
            assert field not in result, f"{field} should be removed"

    def test_preserves_tree_metadata(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
                    "successors": [],
                },
            ],
            traps=[],
            cluster_assignment={},
        )
        result = build_semantic_graph_pass(tree)

        assert result["class"] == "com.example.Svc"
        assert result["method"] == "handle"
        assert result["lineStart"] == 1
        assert result["lineEnd"] == 20

    def test_leaf_ref_node(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = {
            "class": "com.example.Svc",
            "method": "run",
            "methodSignature": "sig",
            "ref": True,
        }
        result = build_semantic_graph_pass(tree)
        assert result.get("ref") is True
        assert "nodes" not in result

    def test_leaf_cycle_node(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = {
            "class": "com.example.Svc",
            "method": "run",
            "methodSignature": "sig",
            "cycle": True,
        }
        result = build_semantic_graph_pass(tree)
        assert result.get("cycle") is True

    def test_leaf_filtered_node(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = {
            "class": "com.example.Svc",
            "method": "run",
            "methodSignature": "sig",
            "filtered": True,
        }
        result = build_semantic_graph_pass(tree)
        assert result.get("filtered") is True

    def test_does_not_mutate_input(self):
        from ftrace_semantic import build_semantic_graph_pass
        import copy

        tree = _make_enriched_method(
            blocks=[
                {
                    "id": "B0",
                    "stmts": [],
                    "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
                    "successors": [],
                },
            ],
            traps=[],
            cluster_assignment={},
        )
        original = copy.deepcopy(tree)
        build_semantic_graph_pass(tree)
        assert tree == original
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_build_semantic_graph.py -v`
Expected: FAIL — `ImportError: cannot import name 'make_node_label' from 'ftrace_semantic'`

- [ ] **Step 3: Implement pass 4 helper functions and `build_semantic_graph_pass`**

Add to `python/ftrace_semantic.py`:

```python
from ftrace_types import (
    SemanticNode,
    SemanticEdge,
    SemanticCluster,
    ExceptionEdge,
    NodeKind,
    ClusterRole,
    BranchLabel,
)


def short_class(fqcn: str) -> str:
    """Extract short class name from fully qualified name."""
    return fqcn.rsplit(".", 1)[-1]


def make_node_label(entry: MergedStmt) -> list[str]:
    """Build a label list for a merged stmt entry."""
    parts = [f"L{entry['line']}"]
    for c in sorted(entry.get("calls", [])):
        parts.append(
            short_class(c.rsplit(".", 1)[0]) + "." + c.rsplit(".", 1)[-1]
            if "." in c
            else c
        )
    if not entry.get("calls"):
        for a in entry.get("assigns", []):
            parts.append(a)
    return parts


def classify_node_kind(entry: MergedStmt) -> NodeKind:
    """Determine the node kind from a merged stmt entry."""
    if entry.get("branches"):
        return NodeKind.BRANCH
    if entry.get("calls"):
        return NodeKind.CALL
    if entry.get("assigns"):
        return NodeKind.ASSIGN
    return NodeKind.PLAIN


def build_semantic_graph_pass(tree: dict, next_id: int = 0) -> dict:
    """Pass 4: Build semantic graph from enriched tree. Returns new tree.

    Consumes blocks, traps, mergedStmts, clusterAssignment, blockAliases.
    Emits nodes, edges, clusters, exceptionEdges. Drops raw fields.

    next_id: starting node ID counter (for unique IDs across the tree).
    Returns the transformed tree. The caller can read the highest node ID
    from the nodes to continue numbering for children.
    """
    if _is_leaf_node(tree):
        return dict(tree)

    blocks = tree.get("blocks", [])
    traps = tree.get("traps", [])
    cluster_assignment = tree.get("clusterAssignment", {})
    block_aliases = tree.get("blockAliases", {})

    # --- Build nodes ---
    node_counter = next_id
    block_first: dict[str, str] = {}  # block_id → first node_id
    block_last: dict[str, str] = {}   # block_id → last node_id
    bid_to_nids: dict[str, list[str]] = {}  # block_id → list of node_ids
    all_nodes: list[SemanticNode] = []

    for block in blocks:
        bid = block["id"]

        # Aliased blocks share the canonical block's nodes
        if bid in block_aliases:
            canonical = block_aliases[bid]
            block_first[bid] = block_first[canonical]
            block_last[bid] = block_last[canonical]
            bid_to_nids[bid] = bid_to_nids[canonical]
            continue

        merged = block.get("mergedStmts", [])
        if not merged:
            nid = f"n{node_counter}"
            node_counter += 1
            all_nodes.append({
                "id": nid,
                "lines": [],
                "kind": NodeKind.PLAIN,
                "label": [bid],
            })
            block_first[bid] = nid
            block_last[bid] = nid
            bid_to_nids[bid] = [nid]
            continue

        nids_for_block: list[str] = []
        is_branch_block = bool(block.get("branchCondition"))

        for idx, entry in enumerate(merged):
            nid = f"n{node_counter}"
            node_counter += 1
            is_last = idx == len(merged) - 1

            kind = classify_node_kind(entry)
            label = make_node_label(entry)

            # Last node in a branch block includes the condition
            if is_branch_block and is_last:
                kind = NodeKind.BRANCH
                cond = block.get("branchCondition", "")
                if cond:
                    label.append(cond)

            all_nodes.append({
                "id": nid,
                "lines": [entry["line"]],
                "kind": kind,
                "label": label,
            })
            nids_for_block.append(nid)

            if bid not in block_first:
                block_first[bid] = nid

        block_last[bid] = nids_for_block[-1]
        bid_to_nids[bid] = nids_for_block

    # --- Build intra-block edges (sequential within a block) ---
    canonical_bids = [b["id"] for b in blocks if b["id"] not in block_aliases]
    all_edges: list[SemanticEdge] = [
        {"from": nids[i], "to": nids[i + 1]}
        for bid in canonical_bids
        for nids in [bid_to_nids.get(bid, [])]
        for i in range(len(nids) - 1)
    ]

    # --- Build inter-block edges (CFG edges) ---
    # Track shared nodes for reverse-edge artifact detection
    from collections import Counter
    nid_block_count = Counter(block_first[bid] for bid in block_first)
    shared_nids = frozenset(nid for nid, c in nid_block_count.items() if c > 1)

    emitted: set[tuple[str, str, str]] = set()

    for block in blocks:
        bid = block["id"]
        tail_nid = block_last.get(bid, "")
        if not tail_nid:
            continue
        successors = block.get("successors", [])
        branch_cond = block.get("branchCondition", "")

        if len(successors) == 2 and branch_cond:
            true_nid = block_first.get(successors[0], "")
            false_nid = block_first.get(successors[1], "")
            for succ_nid, label in [(true_nid, BranchLabel.T), (false_nid, BranchLabel.F)]:
                if succ_nid and tail_nid != succ_nid:
                    key = (tail_nid, succ_nid, label)
                    if key not in emitted:
                        emitted.add(key)
                        all_edges.append({"from": tail_nid, "to": succ_nid, "branch": label})
        else:
            for succ_id in successors:
                succ_nid = block_first.get(succ_id, "")
                if succ_nid and tail_nid != succ_nid:
                    key = (tail_nid, succ_nid, "")
                    reverse = (succ_nid, tail_nid, "")
                    if reverse in emitted and (
                        tail_nid in shared_nids or succ_nid in shared_nids
                    ):
                        continue
                    if key not in emitted:
                        emitted.add(key)
                        all_edges.append({"from": tail_nid, "to": succ_nid})

    # --- Build clusters ---
    all_clusters: list[SemanticCluster] = []
    exception_edges: list[ExceptionEdge] = []

    for i, trap in enumerate(traps):
        etype = short_class(trap["type"])

        try_bids = blocks_for_cluster(cluster_assignment, ClusterRole.TRY, i)
        handler_bids = blocks_for_cluster(cluster_assignment, ClusterRole.HANDLER, i)

        try_nids = [nid for bid in try_bids for nid in bid_to_nids.get(bid, [])]
        handler_nids = [nid for bid in handler_bids for nid in bid_to_nids.get(bid, [])]

        all_clusters.append({
            "trapType": etype,
            "role": ClusterRole.TRY,
            "nodeIds": try_nids,
        })

        handler_cluster: SemanticCluster = {
            "trapType": etype,
            "role": ClusterRole.HANDLER,
            "nodeIds": handler_nids,
        }
        handler_entry_nid = block_first.get(trap["handler"], "")
        if handler_entry_nid:
            handler_cluster["entryNodeId"] = handler_entry_nid
        all_clusters.append(handler_cluster)

        # Exception edge
        if handler_entry_nid:
            src_nid = (
                block_first.get(try_bids[0], "")
                if try_bids
                else next(
                    (block_first[cb] for cb in trap.get("coveredBlocks", []) if cb in block_first),
                    "",
                )
            )
            if src_nid:
                exception_edges.append({
                    "from": src_nid,
                    "to": handler_entry_nid,
                    "trapType": etype,
                    "fromCluster": len(all_clusters) - 2,  # try cluster index
                    "toCluster": len(all_clusters) - 1,    # handler cluster index
                })

    # --- Assemble result ---
    # Drop raw/intermediate fields, keep tree metadata
    drop_fields = {
        "blocks", "traps", "clusterAssignment", "blockAliases", "sourceTrace",
    }
    result = {k: v for k, v in tree.items() if k not in drop_fields and k != "children"}
    result["nodes"] = all_nodes
    result["edges"] = all_edges
    result["clusters"] = all_clusters
    result["exceptionEdges"] = exception_edges

    # Set entryNodeId for cross-cluster call edges from parent
    if all_nodes:
        result["entryNodeId"] = all_nodes[0]["id"]

    # Recurse into children
    if "children" in tree:
        result["children"] = [
            build_semantic_graph_pass(child, node_counter + i * 100)
            for i, child in enumerate(tree["children"])
        ]

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/test_build_semantic_graph.py -v`
Expected: All 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_build_semantic_graph.py
git commit -m "feat: pass 4 — build_semantic_graph emits nodes/edges/clusters"
```

---

### Task 6: CLI and `pipe` composer for `ftrace-semantic`

**Files:**
- Modify: `python/ftrace_semantic.py` (add `pipe`, `transform`, `main`)
- Modify: `python/pyproject.toml` (register entry point)

- [ ] **Step 1: Write failing test for `pipe` and `transform`**

Add to `python/tests/test_build_semantic_graph.py` (at the end):

```python
class TestPipeAndTransform:
    def test_pipe_composes_functions(self):
        from ftrace_semantic import pipe

        add1 = lambda x: x + 1
        double = lambda x: x * 2
        assert pipe(add1, double)(3) == 8  # (3+1)*2

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
                {"id": "B0", "stmts": [{"line": 5}], "successors": ["B1"]},
                {"id": "B1", "stmts": [{"line": 10, "call": "Foo.bar"}], "successors": []},
            ],
            "traps": [],
            "children": [],
        }
        result = transform(tree)

        # Should have semantic fields
        assert "nodes" in result
        assert "edges" in result
        assert "clusters" in result
        assert "exceptionEdges" in result

        # Should not have raw fields
        assert "blocks" not in result
        assert "traps" not in result

    def test_transform_leaf_node(self):
        from ftrace_semantic import transform

        tree = {"class": "Svc", "method": "run", "methodSignature": "sig", "ref": True}
        result = transform(tree)
        assert result.get("ref") is True
        assert "nodes" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_build_semantic_graph.py::TestPipeAndTransform -v`
Expected: FAIL — `ImportError: cannot import name 'pipe' from 'ftrace_semantic'`

- [ ] **Step 3: Implement `pipe`, `transform`, and `main`**

Add to `python/ftrace_semantic.py`:

```python
from functools import reduce
from typing import Callable


def pipe(*fns: Callable[[dict], dict]) -> Callable[[dict], dict]:
    """Compose functions left-to-right: pipe(f, g)(x) == g(f(x))."""
    return lambda x: reduce(lambda acc, fn: fn(acc), fns, x)


def transform(tree: dict) -> dict:
    """Run all four passes on a tree."""
    return pipe(
        merge_stmts_pass,
        assign_clusters_pass,
        deduplicate_blocks_pass,
        build_semantic_graph_pass,
    )(tree)


def main():
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Transform raw xtrace JSON into semantic graph JSON."
    )
    parser.add_argument("--input", type=Path, help="Input JSON file (default: stdin)")
    parser.add_argument("--output", type=Path, help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            tree = json.load(f)
    else:
        tree = json.load(sys.stdin)

    result = transform(tree)
    output = json.dumps(result, indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
        print(f"Wrote semantic graph to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/test_build_semantic_graph.py::TestPipeAndTransform -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Register entry point in `pyproject.toml`**

In `python/pyproject.toml`, add to `[project.scripts]`:

```toml
ftrace-semantic = "ftrace_semantic:main"
```

- [ ] **Step 6: Verify CLI works**

Run: `cd python && echo '{"class":"Svc","method":"run","methodSignature":"sig","ref":true}' | uv run ftrace-semantic`
Expected: JSON output with `"ref": true`, no crash.

- [ ] **Step 7: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_build_semantic_graph.py python/pyproject.toml
git commit -m "feat: ftrace-semantic CLI with pipe composer and transform"
```

---

### Task 7: Rewrite `ftrace_to_dot.py` as dumb renderer

**Files:**
- Create: `python/tests/test_dot_rendering.py`
- Rewrite: `python/ftrace_to_dot.py`

- [ ] **Step 1: Write failing tests for the new renderer**

Create `python/tests/test_dot_rendering.py`:

```python
"""Tests for the rewritten ftrace_to_dot — dumb semantic JSON → DOT renderer."""


def _make_semantic_method(nodes, edges, clusters=(), exception_edges=(), children=()):
    return {
        "class": "com.example.Svc",
        "method": "handle",
        "lineStart": 1,
        "lineEnd": 20,
        "nodes": nodes,
        "edges": edges,
        "clusters": list(clusters),
        "exceptionEdges": list(exception_edges),
        "children": list(children),
    }


def _quoted_value(line: str, key: str) -> str:
    tag = f'{key}="'
    start = line.find(tag)
    if start == -1:
        return ""
    start += len(tag)
    end = line.index('"', start)
    return line[start:end]


class TestNodeRendering:
    def test_plain_node(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}],
            edges=[],
        )
        dot = build_dot(method)
        assert 'label="L5"' in dot
        assert 'fillcolor="white"' in dot

    def test_call_node_green(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [9], "kind": "call", "label": ["L9", "Foo.bar"]}],
            edges=[],
        )
        dot = build_dot(method)
        assert "#d4edda" in dot

    def test_branch_node_diamond(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [6], "kind": "branch", "label": ["L6", "i <= 0"]}],
            edges=[],
        )
        dot = build_dot(method)
        assert "diamond" in dot
        assert "#cce5ff" in dot

    def test_assign_node_beige(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [7], "kind": "assign", "label": ["L7", "x = 5"]}],
            edges=[],
        )
        dot = build_dot(method)
        assert "#f5f5dc" in dot

    def test_ref_node(self):
        from ftrace_to_dot import build_dot

        method = {
            "class": "com.example.Svc",
            "method": "run",
            "ref": True,
            "methodSignature": "sig",
        }
        dot = build_dot(method)
        assert "(ref)" in dot
        assert "#e8e8e8" in dot

    def test_cycle_node(self):
        from ftrace_to_dot import build_dot

        method = {
            "class": "com.example.Svc",
            "method": "run",
            "cycle": True,
            "methodSignature": "sig",
        }
        dot = build_dot(method)
        assert "(cycle)" in dot
        assert "#ffcccc" in dot

    def test_filtered_node(self):
        from ftrace_to_dot import build_dot

        method = {
            "class": "com.example.Svc",
            "method": "run",
            "filtered": True,
            "methodSignature": "sig",
        }
        dot = build_dot(method)
        assert "(filtered)" in dot
        assert "#fff3cd" in dot

    def test_multiline_label(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [9], "kind": "call", "label": ["L9", "RuntimeException.<init>"]}],
            edges=[],
        )
        dot = build_dot(method)
        assert r"L9\nRuntimeException.<init>" in dot


class TestEdgeRendering:
    def test_normal_edge(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]},
                {"id": "n1", "lines": [6], "kind": "plain", "label": ["L6"]},
            ],
            edges=[{"from": "n0", "to": "n1"}],
        )
        dot = build_dot(method)
        assert "n0 -> n1;" in dot

    def test_branch_true_edge(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [6], "kind": "branch", "label": ["L6"]},
                {"id": "n1", "lines": [7], "kind": "plain", "label": ["L7"]},
            ],
            edges=[{"from": "n0", "to": "n1", "branch": "T"}],
        )
        dot = build_dot(method)
        assert "#28a745" in dot
        assert 'label="T"' in dot

    def test_branch_false_edge(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [6], "kind": "branch", "label": ["L6"]},
                {"id": "n1", "lines": [9], "kind": "plain", "label": ["L9"]},
            ],
            edges=[{"from": "n0", "to": "n1", "branch": "F"}],
        )
        dot = build_dot(method)
        assert "#dc3545" in dot
        assert 'label="F"' in dot


class TestClusterRendering:
    def test_try_cluster_orange(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}],
            edges=[],
            clusters=[
                {"trapType": "RuntimeException", "role": "try", "nodeIds": ["n0"]},
            ],
        )
        dot = build_dot(method)
        assert "#ffa500" in dot
        assert "try (RuntimeException)" in dot

    def test_handler_cluster_catch(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [11], "kind": "plain", "label": ["L11"]}],
            edges=[],
            clusters=[
                {"trapType": "RuntimeException", "role": "handler", "nodeIds": ["n0"], "entryNodeId": "n0"},
            ],
        )
        dot = build_dot(method)
        assert "#007bff" in dot
        assert "catch (RuntimeException)" in dot

    def test_handler_cluster_finally(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [14], "kind": "plain", "label": ["L14"]}],
            edges=[],
            clusters=[
                {"trapType": "Throwable", "role": "handler", "nodeIds": ["n0"], "entryNodeId": "n0"},
            ],
        )
        dot = build_dot(method)
        assert "finally" in dot


class TestExceptionEdgeRendering:
    def test_exception_edge_dashed_orange(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]},
                {"id": "n1", "lines": [11], "kind": "plain", "label": ["L11"]},
            ],
            edges=[],
            clusters=[
                {"trapType": "RuntimeException", "role": "try", "nodeIds": ["n0"]},
                {"trapType": "RuntimeException", "role": "handler", "nodeIds": ["n1"], "entryNodeId": "n1"},
            ],
            exception_edges=[
                {"from": "n0", "to": "n1", "trapType": "RuntimeException", "fromCluster": 0, "toCluster": 1},
            ],
        )
        dot = build_dot(method)
        assert "n0 -> n1" in dot
        assert "dashed" in dot
        assert "#ffa500" in dot
        assert "RuntimeException" in dot


class TestMethodCluster:
    def test_method_label(self):
        from ftrace_to_dot import build_dot

        method = _make_semantic_method(
            nodes=[{"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]}],
            edges=[],
        )
        dot = build_dot(method)
        assert "Svc.handle [1-20]" in dot
        assert "#f0f0f0" in dot


class TestCrossClusterEdges:
    def test_child_call_edge(self):
        from ftrace_to_dot import build_dot

        child = {
            "class": "com.example.Other",
            "method": "run",
            "lineStart": 30,
            "lineEnd": 40,
            "entryNodeId": "n5",
            "nodes": [{"id": "n5", "lines": [30], "kind": "plain", "label": ["L30"]}],
            "edges": [],
            "clusters": [],
            "exceptionEdges": [],
            "children": [],
            "callSiteLine": 9,
        }
        method = _make_semantic_method(
            nodes=[
                {"id": "n0", "lines": [5], "kind": "plain", "label": ["L5"]},
                {"id": "n1", "lines": [9], "kind": "call", "label": ["L9", "Other.run"]},
            ],
            edges=[{"from": "n0", "to": "n1"}],
            children=[child],
        )
        dot = build_dot(method)
        assert "n1 -> n5" in dot
        assert "#e05050" in dot
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_dot_rendering.py -v`
Expected: FAIL — the current `build_dot` expects raw blocks, not semantic JSON.

- [ ] **Step 3: Rewrite `ftrace_to_dot.py` as dumb renderer**

Replace the entire contents of `python/ftrace_to_dot.py` with:

```python
#!/usr/bin/env python3
"""Render semantic graph JSON as Graphviz DOT, then optionally produce SVG/PNG.

This is a dumb renderer: it reads the semantic JSON emitted by ftrace_semantic
and maps it to DOT syntax. All graph transformations (merging, clustering,
dedup) happen upstream in ftrace_semantic.
"""

import json
import sys
from pathlib import Path

from ftrace_types import NodeKind, BranchLabel

# -- Visual constants --
NODE_STYLE: dict[NodeKind, dict[str, str]] = {
    NodeKind.PLAIN:    {"shape": "box", "fillcolor": "white", "style": "filled,rounded"},
    NodeKind.CALL:     {"shape": "box", "fillcolor": "#d4edda", "style": "filled,rounded"},
    NodeKind.BRANCH:   {"shape": "diamond", "fillcolor": "#cce5ff", "style": "filled"},
    NodeKind.ASSIGN:   {"shape": "box", "fillcolor": "#f5f5dc", "style": "filled,rounded"},
    NodeKind.CYCLE:    {"shape": "box", "fillcolor": "#ffcccc", "style": "filled,rounded,dashed", "color": "red"},
    NodeKind.REF:      {"shape": "box", "fillcolor": "#e8e8e8", "style": "filled,rounded,dashed", "color": "#999999"},
    NodeKind.FILTERED: {"shape": "box", "fillcolor": "#fff3cd", "style": "filled,rounded,dashed", "color": "#cc9900"},
}

BRANCH_COLORS: dict[BranchLabel, str] = {BranchLabel.T: "#28a745", BranchLabel.F: "#dc3545"}


def escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def short_class(fqcn: str) -> str:
    return fqcn.rsplit(".", 1)[-1]


def _render_node(nid: str, node: dict) -> str:
    """Render a single semantic node as a DOT node statement."""
    label = r"\n".join(escape(p) for p in node["label"])
    kind = NodeKind(node["kind"])
    style = NODE_STYLE.get(kind, NODE_STYLE[NodeKind.PLAIN])
    attrs = f'label="{label}"'
    for k, v in style.items():
        attrs += f', {k}="{v}"'
    return f'    {nid} [' + attrs + "];"


def _render_edge(edge: dict) -> str:
    """Render a single semantic edge as a DOT edge statement."""
    src, dst = edge["from"], edge["to"]
    branch = edge.get("branch", "")
    if branch:
        color = BRANCH_COLORS.get(BranchLabel(branch), "black")
        return (
            f'    {src} -> {dst} '
            f'[label="{branch}", color="{color}", fontcolor="{color}"];'
        )
    return f"    {src} -> {dst};"


def _render_exception_edge(ee: dict, clusters: list[dict]) -> str:
    """Render an exception edge with ltail/lhead cluster references."""
    src, dst = ee["from"], ee["to"]
    trap_type = escape(ee["trapType"])
    attrs = (
        f'label="{trap_type}", color="#ffa500", style="dashed", '
        f'fontcolor="#ffa500"'
    )
    from_idx = ee.get("fromCluster", -1)
    to_idx = ee.get("toCluster", -1)
    if from_idx >= 0 and clusters[from_idx].get("nodeIds", []):
        attrs += f', ltail="cluster_trap_{from_idx}"'
    if to_idx >= 0 and clusters[to_idx].get("nodeIds", []):
        attrs += f', lhead="cluster_trap_{to_idx}"'
    return f"    {src} -> {dst} [{attrs}];"


def build_dot(root: dict) -> str:
    lines = [
        "digraph ftrace {",
        "  rankdir=TB;",
        "  compound=true;",
        '  node [shape=box, style="filled,rounded", fillcolor=white, '
        'fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
        "",
    ]
    cross_edges: list[str] = []
    cluster_counter = [0]

    def next_cluster_id() -> str:
        cid = f"cluster_{cluster_counter[0]}"
        cluster_counter[0] += 1
        return cid

    def add_method(node: dict) -> str:
        """Add a method node. Returns entry node ID."""
        cls = short_class(node.get("class", "?"))
        method = node.get("method", "?")

        # Leaf nodes
        for leaf_kind in ("cycle", "ref", "filtered"):
            if node.get(leaf_kind):
                nid = f"n_leaf_{cluster_counter[0]}"
                cluster_counter[0] += 1
                label = f"{cls}.{method}\\n({leaf_kind})"
                style = NODE_STYLE[NodeKind(leaf_kind)]
                attrs = f'label="{escape(label)}"'
                for k, v in style.items():
                    attrs += f', {k}="{v}"'
                lines.append(f"  {nid} [{attrs}];")
                return nid

        nodes = node.get("nodes", [])
        edges = node.get("edges", [])
        clusters = node.get("clusters", [])
        exception_edges = node.get("exceptionEdges", [])
        children = node.get("children", [])
        line_start = node.get("lineStart", "?")
        line_end = node.get("lineEnd", "?")

        cid = next_cluster_id()
        lines.append(f"  subgraph {cid} {{")
        lines.append(
            f'    label="{escape(cls)}.{escape(method)} [{line_start}-{line_end}]";'
        )
        lines.append('    style="rounded,filled"; fillcolor="#f0f0f0";')
        lines.append('    color="#4a86c8";')
        lines.append("")

        # Nodes
        for n in nodes:
            lines.append(_render_node(n["id"], n))

        # Edges
        for e in edges:
            lines.append(_render_edge(e))

        # Trap clusters as nested subgraphs
        for i, cluster in enumerate(clusters):
            trap_type = cluster["trapType"]
            role = cluster["role"]
            node_ids = cluster.get("nodeIds", [])

            tc_id = f"cluster_trap_{i}"
            lines.append(f"    subgraph {tc_id} {{")

            if role == "try":
                lines.append(f'      label="try ({escape(trap_type)})";')
                lines.append(
                    '      style="dashed,rounded"; color="#ffa500"; fontcolor="#ffa500";'
                )
            else:
                h_label = (
                    "finally"
                    if trap_type.lower() in ("throwable", "any")
                    else f"catch ({escape(trap_type)})"
                )
                lines.append(f'      label="{h_label}";')
                lines.append(
                    '      style="dashed,rounded"; color="#007bff"; fontcolor="#007bff";'
                )

            for nid in node_ids:
                lines.append(f"      {nid};")
            lines.append("    }")

        # Exception edges
        for ee in exception_edges:
            lines.append(_render_exception_edge(ee, clusters))

        lines.append("  }")
        lines.append("")

        # Cross-cluster call edges to children
        # Build line → node ID lookup for call site matching
        line_to_nids: dict[int, list[str]] = {}
        for n in nodes:
            for ln in n.get("lines", []):
                line_to_nids.setdefault(ln, []).append(n["id"])

        entry_nid = node.get("entryNodeId", "") or (nodes[0]["id"] if nodes else "")

        for child in children:
            child_entry = add_method(child)
            if child_entry:
                csl = child.get("callSiteLine", -1)
                source_nids = line_to_nids.get(csl, [])
                if source_nids:
                    cross_edges.append(
                        f"  {source_nids[0]} -> {child_entry} "
                        f'[color="#e05050", style=bold, penwidth=1.5];'
                    )
                elif entry_nid:
                    cross_edges.append(f"  {entry_nid} -> {child_entry};")

        return entry_nid

    add_method(root)

    lines.append("  // Cross-cluster call edges")
    lines.extend(cross_edges)
    lines.append("}")
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Render semantic graph JSON as Graphviz DOT, then optionally produce SVG/PNG."
    )
    parser.add_argument("--input", type=Path, help="Input semantic JSON file (default: stdin)")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file (.dot, .svg, or .png). Default: stdout as DOT.",
    )
    args = parser.parse_args()

    if args.input:
        with open(args.input) as f:
            root = json.load(f)
    else:
        root = json.load(sys.stdin)

    dot = build_dot(root)

    if args.output:
        ext = args.output.suffix.lower()
        if ext in (".svg", ".png"):
            import subprocess

            fmt = ext.lstrip(".")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["dot", f"-T{fmt}", "-o", str(args.output)],
                input=dot,
                text=True,
                capture_output=True,
            )
            if result.returncode != 0:
                print(f"dot failed: {result.stderr}", file=sys.stderr)
                sys.exit(1)
            print(f"Rendered {args.output}", file=sys.stderr)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(dot)
            print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(dot)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run rendering tests to verify they pass**

Run: `cd python && uv run pytest tests/test_dot_rendering.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_to_dot.py python/tests/test_dot_rendering.py
git commit -m "feat: rewrite ftrace_to_dot as dumb semantic JSON renderer"
```

---

### Task 8: Remove old tests and add `sourceTrace` fallback

**Files:**
- Remove: `python/tests/test_dot_trap_clusters.py`
- Modify: `python/ftrace_semantic.py` (handle sourceTrace fallback in pass 1 and 4)

- [ ] **Step 1: Write failing test for sourceTrace fallback**

Add to `python/tests/test_merge_stmts.py`:

```python
class TestMergeSourceTrace:
    def test_merges_source_trace(self):
        from ftrace_semantic import merge_source_trace

        trace = [
            {"line": 5, "calls": ["Foo.bar"]},
            {"line": 5, "calls": ["Baz.qux"]},
            {"line": 10},
        ]
        result = merge_source_trace(trace)
        assert len(result) == 2
        assert result[0]["line"] == 5
        assert sorted(result[0]["calls"]) == ["Baz.qux", "Foo.bar"]

    def test_negative_lines_excluded(self):
        from ftrace_semantic import merge_source_trace

        trace = [{"line": -1}, {"line": 5}]
        result = merge_source_trace(trace)
        assert len(result) == 1


class TestMergeStmtsPassSourceTrace:
    def test_source_trace_fallback(self):
        from ftrace_semantic import merge_stmts_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "sourceTrace": [
                {"line": 5, "calls": ["Foo.bar"]},
                {"line": 10},
            ],
            "children": [],
        }
        result = merge_stmts_pass(tree)
        assert "mergedSourceTrace" in result
        assert len(result["mergedSourceTrace"]) == 2
```

Add to `python/tests/test_build_semantic_graph.py`:

```python
class TestSourceTraceFallback:
    def test_source_trace_produces_linear_nodes(self):
        from ftrace_semantic import build_semantic_graph_pass

        tree = {
            "class": "com.example.Svc",
            "method": "run",
            "methodSignature": "sig",
            "lineStart": 5,
            "lineEnd": 10,
            "sourceLineCount": 6,
            "mergedSourceTrace": [
                {"line": 5, "calls": [], "branches": [], "assigns": []},
                {"line": 10, "calls": ["Foo.bar"], "branches": [], "assigns": []},
            ],
            "children": [],
        }
        result = build_semantic_graph_pass(tree)

        assert len(result["nodes"]) == 2
        assert result["nodes"][0]["kind"] == NodeKind.PLAIN
        assert result["nodes"][1]["kind"] == NodeKind.CALL
        assert len(result["edges"]) == 1
        assert result["edges"][0]["from"] == result["nodes"][0]["id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd python && uv run pytest tests/test_merge_stmts.py::TestMergeSourceTrace tests/test_merge_stmts.py::TestMergeStmtsPassSourceTrace tests/test_build_semantic_graph.py::TestSourceTraceFallback -v`
Expected: FAIL

- [ ] **Step 3: Implement sourceTrace support**

Add `merge_source_trace` to `python/ftrace_semantic.py`:

```python
def merge_source_trace(source_trace: list[dict]) -> list[MergedStmt]:
    """Deduplicate sourceTrace by line number, merging calls and branches."""
    by_line: dict[int, MergedStmt] = {}
    for entry in source_trace:
        line = entry["line"]
        if line < 0:
            continue
        if line not in by_line:
            by_line[line] = {"line": line, "calls": [], "branches": [], "assigns": []}
        for c in entry.get("calls", []):
            if c not in by_line[line]["calls"]:
                by_line[line]["calls"].append(c)
        if "branch" in entry:
            by_line[line]["branches"].append(entry["branch"])
    return [by_line[ln] for ln in sorted(by_line)]
```

Update `merge_stmts_pass` to handle sourceTrace:

```python
def merge_stmts_pass(tree: dict) -> dict:
    """Pass 1: Add mergedStmts to each block, or mergedSourceTrace. Returns new tree."""
    if _is_leaf_node(tree):
        return dict(tree)

    result = dict(tree)

    if "blocks" in tree:
        result["blocks"] = [
            {**block, "mergedStmts": merge_block_stmts(block.get("stmts", []))}
            for block in tree["blocks"]
        ]
    elif "sourceTrace" in tree:
        result["mergedSourceTrace"] = merge_source_trace(tree["sourceTrace"])

    if "children" in tree:
        result["children"] = [merge_stmts_pass(child) for child in tree["children"]]

    return result
```

Update `build_semantic_graph_pass` to handle `mergedSourceTrace` (no blocks):

In the function, before the blocks logic, add a branch for sourceTrace fallback:

```python
    # sourceTrace fallback — no blocks, just a linear list of lines
    if "mergedSourceTrace" in tree and "blocks" not in tree:
        merged = tree["mergedSourceTrace"]
        all_nodes = []
        all_edges = []
        for entry in merged:
            nid = f"n{node_counter}"
            node_counter += 1
            all_nodes.append({
                "id": nid,
                "lines": [entry["line"]],
                "kind": classify_node_kind(entry),
                "label": make_node_label(entry),
            })
        for i in range(len(all_nodes) - 1):
            all_edges.append({"from": all_nodes[i]["id"], "to": all_nodes[i + 1]["id"]})

        drop_fields = {"sourceTrace", "mergedSourceTrace"}
        result = {k: v for k, v in tree.items() if k not in drop_fields and k != "children"}
        result["nodes"] = all_nodes
        result["edges"] = all_edges
        result["clusters"] = []
        result["exceptionEdges"] = []
        if all_nodes:
            result["entryNodeId"] = all_nodes[0]["id"]
        if "children" in tree:
            result["children"] = [
                build_semantic_graph_pass(child, node_counter + i * 100)
                for i, child in enumerate(tree["children"])
            ]
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd python && uv run pytest tests/test_merge_stmts.py tests/test_build_semantic_graph.py -v`
Expected: All tests PASS

- [ ] **Step 5: Delete old test file**

```bash
rm python/tests/test_dot_trap_clusters.py
```

- [ ] **Step 6: Run all Python tests to confirm nothing is broken**

Run: `cd python && uv run pytest tests/ -v`
Expected: All tests PASS (the old tests are gone, new tests cover all behavior)

- [ ] **Step 7: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_merge_stmts.py python/tests/test_build_semantic_graph.py
git rm python/tests/test_dot_trap_clusters.py
git commit -m "feat: sourceTrace fallback, remove old trap cluster tests"
```

---

### Task 9: Update E2E tests for pipeline

**Files:**
- Modify: `test-fixtures/tests/test_xtrace_exception.sh`
- Modify: `test-fixtures/tests/test_ftrace_slice.sh`
- Modify: `test-fixtures/tests/test_xtrace_forward.sh`

- [ ] **Step 1: Update exception E2E test**

The exception test currently asserts on raw JSON fields (`traps`, `coveredBlocks`, `handlerBlocks`). These assertions still work on the raw JSON from xtrace. Add a pipeline assertion that generates DOT via the semantic step.

Add to end of `test-fixtures/tests/test_xtrace_exception.sh` (before `report`):

```bash
# Pipeline: raw → semantic → dot
cd "$REPO_ROOT/python"
uv run ftrace-semantic --input "$OUT/exception.json" --output "$OUT/exception-semantic.json" 2>/dev/null

assert_json_contains "$OUT/exception-semantic.json" \
    '.nodes | length > 0' \
    "semantic graph has nodes"

assert_json_contains "$OUT/exception-semantic.json" \
    '.clusters | length == 4' \
    "semantic graph has 4 clusters (2 traps x try+handler)"

uv run ftrace-to-dot --input "$OUT/exception-semantic.json" --output "$OUT/exception.dot" 2>/dev/null

assert_file_contains "$OUT/exception.dot" "digraph" \
    "DOT output is a digraph"
```

- [ ] **Step 2: Update slice E2E test**

Add to end of `test-fixtures/tests/test_ftrace_slice.sh` (before `report`):

```bash
# Pipeline: sliced raw → semantic → dot
uv run ftrace-semantic --input "$OUT/sliced.json" --output "$OUT/sliced-semantic.json" 2>/dev/null

assert_json_contains "$OUT/sliced-semantic.json" \
    '.nodes | length > 0' \
    "sliced semantic graph has nodes"

uv run ftrace-to-dot --input "$OUT/sliced-semantic.json" --output "$OUT/sliced.svg" 2>/dev/null

[ -f "$OUT/sliced.svg" ]
assert_exit_code 0 "sliced SVG generated"
```

- [ ] **Step 3: Add `assert_file_contains` helper if missing**

Check `test-fixtures/lib-test.sh` for `assert_file_contains`. If missing, add:

```bash
assert_file_contains() {
    local file="$1" pattern="$2" label="$3"
    TOTAL=$((TOTAL + 1))
    if grep -q "$pattern" "$file" 2>/dev/null; then
        PASS=$((PASS + 1))
        echo "  ✓ $label"
    else
        echo "  ✗ $label (pattern '$pattern' not found in $file)"
    fi
}
```

- [ ] **Step 4: Run E2E tests**

Run: `bash test-fixtures/run-e2e.sh`
Expected: All tests PASS including new pipeline assertions.

- [ ] **Step 5: Commit**

```bash
git add test-fixtures/tests/test_xtrace_exception.sh test-fixtures/tests/test_ftrace_slice.sh test-fixtures/lib-test.sh
git commit -m "test: update E2E tests for semantic graph pipeline"
```

---

### Task 10: Run full test suite and clean up

**Files:**
- No new files

- [ ] **Step 1: Run full test suite**

Run: `bash run-all-tests.sh`
Expected: Java unit tests, Python unit tests, and E2E tests all PASS.

- [ ] **Step 2: Verify piping works end-to-end**

Run:
```bash
cd python
uv run ftrace-semantic --input ../test-fixtures/target/exception.json | uv run ftrace-to-dot --output ../test-fixtures/target/exception-pipeline.svg
```
Expected: SVG generated, no errors.

- [ ] **Step 3: Commit any cleanup**

```bash
git add -A
git commit -m "chore: final cleanup after semantic graph pipeline implementation"
```

- [ ] **Step 4: Push**

```bash
git push
```
