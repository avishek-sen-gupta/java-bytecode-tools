# Decompose build_semantic_graph_pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `build_semantic_graph_pass` (255 lines, 5 responsibilities) into 4 focused pure functions plus a thin orchestrator.

**Architecture:** Extract `_resolve_inputs`, `_build_nodes`, `_build_edges`, `_build_clusters` as module-private pure functions communicating via internal TypedDicts. The orchestrator calls resolve → nodes → edges → clusters → assemble. The sourceTrace fallback stays inline as an early-return. All mutating loops are refactored to FP style (comprehensions, reduce, frozenset).

**Tech Stack:** Python 3.13+, pytest, TypedDict, functools.reduce

**Spec:** `docs/superpowers/specs/2026-04-27-decompose-build-semantic-graph-design.md`

---

## File Map

- **Modify:** `python/ftrace_semantic.py` — add constants, type aliases, internal TypedDicts, extract 4 functions, refactor orchestrator
- **Modify:** `python/tests/test_build_semantic_graph.py` — add unit test classes for each extracted function

---

### Task 1: Add field-name constants and type aliases

**Files:**
- Modify: `python/ftrace_semantic.py:10-28` (imports and module-level definitions)

- [ ] **Step 1: Add field-name constants after imports**

In `python/ftrace_semantic.py`, after the import block (line 28), add:

```python
# --- Field-name constants (raw-tree dict keys) ---
_F_BLOCKS = "blocks"
_F_EDGES = "edges"
_F_TRAPS = "traps"
_F_METADATA = "metadata"
_F_SOURCE_TRACE = "sourceTrace"
_F_CHILDREN = "children"
_F_MERGED_SOURCE_TRACE = "mergedSourceTrace"
_F_CLUSTER_ASSIGNMENT = "clusterAssignment"
_F_BLOCK_ALIASES = "blockAliases"

# --- Domain type aliases ---
BlockId = str
NodeId = str
```

- [ ] **Step 2: Move inline import to module level**

Move `from collections import Counter` from line 400 (inside `build_semantic_graph_pass`) to the top of the file, after `from functools import reduce` on line 10:

```python
from collections import Counter
from functools import reduce
```

- [ ] **Step 3: Run tests to verify no regressions**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/test_build_semantic_graph.py -v`
Expected: All existing tests PASS (constants and aliases are additive, inline import move is safe).

- [ ] **Step 4: Commit**

```bash
git add python/ftrace_semantic.py
git commit -m "refactor: add field-name constants and domain type aliases to ftrace_semantic"
```

---

### Task 2: Add internal TypedDicts

**Files:**
- Modify: `python/ftrace_semantic.py` (after constants, before `_is_leaf_node`)

- [ ] **Step 1: Add the four internal TypedDicts**

After the `BlockId`/`NodeId` aliases and before `def _is_leaf_node`, add:

```python
from typing import TypedDict


class _ResolvedInput(TypedDict):
    """Normalized inputs for the semantic graph builders."""

    blocks: list[RawBlock]
    edges: list[RawBlockEdge]
    traps: list[RawTrap]
    cluster_assignment: dict[BlockId, ClusterAssignment]
    block_aliases: dict[BlockId, BlockId]


class _NodeBuildResult(TypedDict):
    """Output of _build_nodes: semantic nodes plus block→node index maps."""

    nodes: list[SemanticNode]
    block_first: dict[BlockId, NodeId]
    block_last: dict[BlockId, NodeId]
    bid_to_nids: dict[BlockId, list[NodeId]]
    node_counter: int


class _EdgeBuildResult(TypedDict):
    """Output of _build_edges: all semantic edges (intra-block + inter-block)."""

    edges: list[SemanticEdge]


class _ClusterBuildResult(TypedDict):
    """Output of _build_clusters: clusters and exception edges."""

    clusters: list[SemanticCluster]
    exception_edges: list[ExceptionEdge]
```

Note: `RawBlockEdge` must be added to the import block at the top:

```python
from ftrace_types import (
    ClusterAssignment,
    ClusterRole,
    BranchLabel,
    ExceptionEdge,
    MergedStmt,
    MethodSemanticCFG,
    NodeKind,
    RawBlock,
    RawBlockEdge,
    RawStmt,
    RawTrap,
    SemanticCluster,
    SemanticEdge,
    SemanticNode,
    SourceTraceEntry,
    MethodCFG,
)
```

Also add `TypedDict` to the `typing` import. Since `TypedDict` is already imported via `ftrace_types`, add a direct import:

```python
from typing import TypedDict
```

- [ ] **Step 2: Run tests to verify no regressions**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/test_build_semantic_graph.py -v`
Expected: All existing tests PASS (TypedDicts are additive).

- [ ] **Step 3: Commit**

```bash
git add python/ftrace_semantic.py
git commit -m "refactor: add internal TypedDicts for semantic graph builder communication"
```

---

### Task 3: Extract `_resolve_inputs`

**Files:**
- Modify: `python/ftrace_semantic.py`
- Test: `python/tests/test_build_semantic_graph.py`

- [ ] **Step 1: Write the failing test**

In `python/tests/test_build_semantic_graph.py`, add:

```python
class TestResolveInputs:
    def test_extracts_all_fields(self):
        from ftrace_semantic import _resolve_inputs

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0", "stmts": [], "mergedStmts": []}],
            "edges": [{"fromBlock": "B0", "toBlock": "B1"}],
            "traps": [{"type": "Ex", "handler": "B1", "coveredBlocks": ["B0"], "handlerBlocks": ["B1"]}],
        }
        metadata = {
            "clusterAssignment": {"B0": {"kind": "try", "trapIndex": 0}},
            "blockAliases": {"B2": "B0"},
        }
        result = _resolve_inputs(tree, metadata)
        assert result["blocks"] == tree["blocks"]
        assert result["edges"] == tree["edges"]
        assert result["traps"] == tree["traps"]
        assert result["cluster_assignment"] == metadata["clusterAssignment"]
        assert result["block_aliases"] == metadata["blockAliases"]

    def test_defaults_when_fields_missing(self):
        from ftrace_semantic import _resolve_inputs

        result = _resolve_inputs({"class": "Svc"}, {})
        assert result["blocks"] == []
        assert result["edges"] == []
        assert result["traps"] == []
        assert result["cluster_assignment"] == {}
        assert result["block_aliases"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/test_build_semantic_graph.py::TestResolveInputs -v`
Expected: FAIL with `ImportError: cannot import name '_resolve_inputs'`

- [ ] **Step 3: Implement `_resolve_inputs`**

In `python/ftrace_semantic.py`, add before `build_semantic_graph_pass`:

```python
def _resolve_inputs(tree: MethodCFG, tree_metadata: dict) -> _ResolvedInput:
    """Extract and normalize raw inputs for the semantic graph builders."""
    return {
        "blocks": tree.get(_F_BLOCKS, []),
        "edges": tree.get(_F_EDGES, []),
        "traps": tree.get(_F_TRAPS, []),
        "cluster_assignment": tree_metadata.get(_F_CLUSTER_ASSIGNMENT, {}),
        "block_aliases": tree_metadata.get(_F_BLOCK_ALIASES, {}),
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/test_build_semantic_graph.py::TestResolveInputs tests/test_build_semantic_graph.py::TestBuildSemanticGraphPass -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_build_semantic_graph.py
git commit -m "refactor: extract _resolve_inputs from build_semantic_graph_pass"
```

---

### Task 4: Extract `_build_nodes`

**Files:**
- Modify: `python/ftrace_semantic.py:320-387`
- Test: `python/tests/test_build_semantic_graph.py`

- [ ] **Step 1: Write the failing tests**

In `python/tests/test_build_semantic_graph.py`, add:

```python
class TestBuildNodes:
    def test_single_block_single_stmt(self):
        from ftrace_semantic import _build_nodes

        blocks = [
            {
                "id": "B0",
                "stmts": [],
                "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
            }
        ]
        result = _build_nodes(blocks, {}, 0)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "n0"
        assert result["nodes"][0]["kind"] == NodeKind.PLAIN
        assert result["block_first"] == {"B0": "n0"}
        assert result["block_last"] == {"B0": "n0"}
        assert result["bid_to_nids"] == {"B0": ["n0"]}
        assert result["node_counter"] == 1

    def test_aliased_block_shares_canonical_nodes(self):
        from ftrace_semantic import _build_nodes

        blocks = [
            {
                "id": "B0",
                "stmts": [],
                "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
            },
            {
                "id": "B1",
                "stmts": [],
                "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
            },
        ]
        result = _build_nodes(blocks, {"B1": "B0"}, 0)
        assert len(result["nodes"]) == 1
        assert result["block_first"]["B1"] == result["block_first"]["B0"]
        assert result["block_last"]["B1"] == result["block_last"]["B0"]

    def test_empty_merged_stmts_produces_placeholder(self):
        from ftrace_semantic import _build_nodes

        blocks = [{"id": "B0", "stmts": [], "mergedStmts": []}]
        result = _build_nodes(blocks, {}, 0)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["kind"] == NodeKind.PLAIN
        assert result["nodes"][0]["label"] == ["B0"]
        assert result["nodes"][0]["lines"] == []

    def test_branch_block_last_node_is_branch_kind(self):
        from ftrace_semantic import _build_nodes

        blocks = [
            {
                "id": "B0",
                "stmts": [],
                "mergedStmts": [
                    {"line": 6, "calls": [], "branches": ["i <= 0"], "assigns": []},
                ],
                "branchCondition": "i <= 0",
            }
        ]
        result = _build_nodes(blocks, {}, 0)
        assert result["nodes"][0]["kind"] == NodeKind.BRANCH
        assert "i <= 0" in result["nodes"][0]["label"]

    def test_next_id_offsets_node_ids(self):
        from ftrace_semantic import _build_nodes

        blocks = [
            {
                "id": "B0",
                "stmts": [],
                "mergedStmts": [{"line": 5, "calls": [], "branches": [], "assigns": []}],
            }
        ]
        result = _build_nodes(blocks, {}, 42)
        assert result["nodes"][0]["id"] == "n42"
        assert result["node_counter"] == 43

    def test_multi_stmt_block_produces_sequential_nodes(self):
        from ftrace_semantic import _build_nodes

        blocks = [
            {
                "id": "B0",
                "stmts": [],
                "mergedStmts": [
                    {"line": 5, "calls": [], "branches": [], "assigns": []},
                    {"line": 6, "calls": ["Foo.bar"], "branches": [], "assigns": []},
                ],
            }
        ]
        result = _build_nodes(blocks, {}, 0)
        assert len(result["nodes"]) == 2
        assert result["block_first"]["B0"] == "n0"
        assert result["block_last"]["B0"] == "n1"
        assert result["bid_to_nids"]["B0"] == ["n0", "n1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/test_build_semantic_graph.py::TestBuildNodes -v`
Expected: FAIL with `ImportError: cannot import name '_build_nodes'`

- [ ] **Step 3: Implement `_build_nodes`**

In `python/ftrace_semantic.py`, add before `_resolve_inputs`:

```python
def _process_block_stmts(
    merged: list[MergedStmt], is_branch_block: bool, branch_condition: str, start_id: int
) -> list[SemanticNode]:
    """Build semantic nodes for one block's merged statements."""
    last_idx = len(merged) - 1
    return [
        {
            "id": f"n{start_id + idx}",
            "lines": [entry["line"]],
            "kind": (
                NodeKind.BRANCH
                if is_branch_block and idx == last_idx
                else classify_node_kind(entry)
            ),
            "label": (
                make_node_label(entry) + ([branch_condition] if branch_condition else [])
                if is_branch_block and idx == last_idx
                else make_node_label(entry)
            ),
        }
        for idx, entry in enumerate(merged)
    ]


def _build_nodes(
    blocks: list[RawBlock], block_aliases: dict[BlockId, BlockId], next_id: int
) -> _NodeBuildResult:
    """Build semantic nodes from blocks. Pure function.

    Processes each block's merged statements into semantic nodes,
    handling aliased blocks and empty blocks. Returns nodes plus
    block→node index maps.
    """

    def fold_block(acc: tuple[list[SemanticNode], dict[BlockId, NodeId], dict[BlockId, NodeId], dict[BlockId, list[NodeId]], int], block: RawBlock) -> tuple[list[SemanticNode], dict[BlockId, NodeId], dict[BlockId, NodeId], dict[BlockId, list[NodeId]], int]:
        nodes, first, last, bid_nids, counter = acc
        bid = block["id"]

        # Aliased blocks share the canonical block's nodes
        if bid in block_aliases:
            canonical = block_aliases[bid]
            return (
                nodes,
                {**first, bid: first[canonical]},
                {**last, bid: last[canonical]},
                {**bid_nids, bid: bid_nids[canonical]},
                counter,
            )

        merged = block.get("mergedStmts", [])

        # Empty block: placeholder node
        if not merged:
            nid = f"n{counter}"
            placeholder: SemanticNode = {
                "id": nid,
                "lines": [],
                "kind": NodeKind.PLAIN,
                "label": [bid],
            }
            return (
                [*nodes, placeholder],
                {**first, bid: nid},
                {**last, bid: nid},
                {**bid_nids, bid: [nid]},
                counter + 1,
            )

        # Normal block: build nodes from merged statements
        block_nodes = _process_block_stmts(
            merged,
            bool(block.get("branchCondition")),
            block.get("branchCondition", ""),
            counter,
        )
        nids = [n["id"] for n in block_nodes]
        return (
            [*nodes, *block_nodes],
            {**first, bid: nids[0]},
            {**last, bid: nids[-1]},
            {**bid_nids, bid: nids},
            counter + len(block_nodes),
        )

    all_nodes, block_first, block_last, bid_to_nids, node_counter = reduce(
        fold_block, blocks, ([], {}, {}, {}, next_id)
    )

    return {
        "nodes": all_nodes,
        "block_first": block_first,
        "block_last": block_last,
        "bid_to_nids": bid_to_nids,
        "node_counter": node_counter,
    }
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/test_build_semantic_graph.py::TestBuildNodes tests/test_build_semantic_graph.py::TestBuildSemanticGraphPass -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_build_semantic_graph.py
git commit -m "refactor: extract _build_nodes from build_semantic_graph_pass"
```

---

### Task 5: Extract `_build_edges`

**Files:**
- Modify: `python/ftrace_semantic.py:389-432`
- Test: `python/tests/test_build_semantic_graph.py`

- [ ] **Step 1: Write the failing tests**

In `python/tests/test_build_semantic_graph.py`, add:

```python
class TestBuildEdges:
    def test_intra_block_sequential_edges(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[],
            block_first={"B0": "n0"},
            block_last={"B0": "n1"},
            bid_to_nids={"B0": ["n0", "n1"]},
            block_aliases={},
        )
        assert result["edges"] == [{"from": "n0", "to": "n1"}]

    def test_inter_block_unconditional_edge(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[{"fromBlock": "B0", "toBlock": "B1"}],
            block_first={"B0": "n0", "B1": "n1"},
            block_last={"B0": "n0", "B1": "n1"},
            bid_to_nids={"B0": ["n0"], "B1": ["n1"]},
            block_aliases={},
        )
        unconditional = [e for e in result["edges"] if "branch" not in e]
        assert {"from": "n0", "to": "n1"} in unconditional

    def test_branch_edges_with_labels(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[
                {"fromBlock": "B0", "toBlock": "B1", "label": "T"},
                {"fromBlock": "B0", "toBlock": "B2", "label": "F"},
            ],
            block_first={"B0": "n0", "B1": "n1", "B2": "n2"},
            block_last={"B0": "n0", "B1": "n1", "B2": "n2"},
            bid_to_nids={"B0": ["n0"], "B1": ["n1"], "B2": ["n2"]},
            block_aliases={},
        )
        branch_edges = [e for e in result["edges"] if "branch" in e]
        labels = {e["branch"] for e in branch_edges}
        assert labels == {"T", "F"}

    def test_self_loop_suppressed(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[{"fromBlock": "B0", "toBlock": "B1"}],
            block_first={"B0": "n0", "B1": "n0"},
            block_last={"B0": "n0", "B1": "n0"},
            bid_to_nids={"B0": ["n0"], "B1": ["n0"]},
            block_aliases={"B1": "B0"},
        )
        inter_edges = [
            e for e in result["edges"]
            if e.get("from") != e.get("to")
            or "branch" in e
        ]
        self_loops = [e for e in result["edges"] if e["from"] == e["to"]]
        assert self_loops == []

    def test_duplicate_edges_deduplicated(self):
        from ftrace_semantic import _build_edges

        result = _build_edges(
            raw_edges=[
                {"fromBlock": "B0", "toBlock": "B1"},
                {"fromBlock": "B0", "toBlock": "B1"},
            ],
            block_first={"B0": "n0", "B1": "n1"},
            block_last={"B0": "n0", "B1": "n1"},
            bid_to_nids={"B0": ["n0"], "B1": ["n1"]},
            block_aliases={},
        )
        unconditional = [e for e in result["edges"] if "branch" not in e]
        assert len(unconditional) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/test_build_semantic_graph.py::TestBuildEdges -v`
Expected: FAIL with `ImportError: cannot import name '_build_edges'`

- [ ] **Step 3: Implement `_build_edges`**

In `python/ftrace_semantic.py`, add after `_build_nodes`:

```python
def _build_intra_block_edges(
    bid_to_nids: dict[BlockId, list[NodeId]], block_aliases: dict[BlockId, BlockId]
) -> list[SemanticEdge]:
    """Build sequential edges within each canonical block."""
    return [
        {"from": nids[i], "to": nids[i + 1]}
        for bid, nids in bid_to_nids.items()
        if bid not in block_aliases
        for i in range(len(nids) - 1)
    ]


def _build_inter_block_edges(
    raw_edges: list[RawBlockEdge],
    block_first: dict[BlockId, NodeId],
    block_last: dict[BlockId, NodeId],
) -> list[SemanticEdge]:
    """Build edges between blocks from raw CFG edges. Deduplicates and suppresses self-loops."""
    nid_block_count = Counter(nid for nid in block_first.values())
    shared_nids = frozenset(nid for nid, c in nid_block_count.items() if c > 1)

    def fold_edge(
        acc: tuple[list[SemanticEdge], frozenset[tuple[str, str, str]]],
        raw_edge: RawBlockEdge,
    ) -> tuple[list[SemanticEdge], frozenset[tuple[str, str, str]]]:
        edges, emitted = acc
        tail_nid = block_last.get(raw_edge["fromBlock"], "")
        succ_nid = block_first.get(raw_edge["toBlock"], "")
        if not tail_nid or not succ_nid or tail_nid == succ_nid:
            return (edges, emitted)

        label = raw_edge.get("label", "")
        if label:
            key = (tail_nid, succ_nid, label)
            if key in emitted:
                return (edges, emitted)
            return (
                [*edges, {"from": tail_nid, "to": succ_nid, "branch": BranchLabel(label)}],
                emitted | frozenset([key]),
            )

        key = (tail_nid, succ_nid, "")
        reverse = (succ_nid, tail_nid, "")
        if reverse in emitted and (tail_nid in shared_nids or succ_nid in shared_nids):
            return (edges, emitted)
        if key in emitted:
            return (edges, emitted)
        return (
            [*edges, {"from": tail_nid, "to": succ_nid}],
            emitted | frozenset([key]),
        )

    result_edges, _ = reduce(fold_edge, raw_edges, ([], frozenset()))
    return result_edges


def _build_edges(
    raw_edges: list[RawBlockEdge],
    block_first: dict[BlockId, NodeId],
    block_last: dict[BlockId, NodeId],
    bid_to_nids: dict[BlockId, list[NodeId]],
    block_aliases: dict[BlockId, BlockId],
) -> _EdgeBuildResult:
    """Build all semantic edges: intra-block sequential + inter-block CFG."""
    intra = _build_intra_block_edges(bid_to_nids, block_aliases)
    inter = _build_inter_block_edges(raw_edges, block_first, block_last)
    return {"edges": [*intra, *inter]}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/test_build_semantic_graph.py::TestBuildEdges tests/test_build_semantic_graph.py::TestBuildSemanticGraphPass -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_build_semantic_graph.py
git commit -m "refactor: extract _build_edges from build_semantic_graph_pass"
```

---

### Task 6: Extract `_build_clusters`

**Files:**
- Modify: `python/ftrace_semantic.py:434-488`
- Test: `python/tests/test_build_semantic_graph.py`

- [ ] **Step 1: Write the failing tests**

In `python/tests/test_build_semantic_graph.py`, add:

```python
class TestBuildClusters:
    def test_single_trap_produces_try_and_handler_clusters(self):
        from ftrace_semantic import _build_clusters

        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B3",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B3"],
            }
        ]
        cluster_assignment = {
            "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
        }
        bid_to_nids = {"B0": ["n0"], "B3": ["n1"]}
        block_first = {"B0": "n0", "B3": "n1"}

        result = _build_clusters(traps, cluster_assignment, bid_to_nids, block_first)
        assert len(result["clusters"]) == 2

        try_cluster = [c for c in result["clusters"] if c["role"] == ClusterRole.TRY][0]
        handler_cluster = [c for c in result["clusters"] if c["role"] == ClusterRole.HANDLER][0]
        assert try_cluster["trapType"] == "RuntimeException"
        assert try_cluster["nodeIds"] == ["n0"]
        assert handler_cluster["trapType"] == "RuntimeException"
        assert handler_cluster["nodeIds"] == ["n1"]
        assert handler_cluster["entryNodeId"] == "n1"

    def test_exception_edge_emitted(self):
        from ftrace_semantic import _build_clusters

        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B3",
                "coveredBlocks": ["B0"],
                "handlerBlocks": ["B3"],
            }
        ]
        cluster_assignment = {
            "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
        }
        bid_to_nids = {"B0": ["n0"], "B3": ["n1"]}
        block_first = {"B0": "n0", "B3": "n1"}

        result = _build_clusters(traps, cluster_assignment, bid_to_nids, block_first)
        assert len(result["exception_edges"]) == 1
        ee = result["exception_edges"][0]
        assert ee["from"] == "n0"
        assert ee["to"] == "n1"
        assert ee["trapType"] == "RuntimeException"
        assert ee["fromCluster"] == 0
        assert ee["toCluster"] == 1

    def test_no_traps_produces_empty(self):
        from ftrace_semantic import _build_clusters

        result = _build_clusters([], {}, {}, {})
        assert result["clusters"] == []
        assert result["exception_edges"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/test_build_semantic_graph.py::TestBuildClusters -v`
Expected: FAIL with `ImportError: cannot import name '_build_clusters'`

- [ ] **Step 3: Implement `_build_clusters`**

In `python/ftrace_semantic.py`, add after `_build_edges`:

```python
def _build_trap_clusters(
    trap_index: int,
    trap: RawTrap,
    cluster_assignment: dict[BlockId, ClusterAssignment],
    bid_to_nids: dict[BlockId, list[NodeId]],
    block_first: dict[BlockId, NodeId],
    cluster_offset: int,
) -> tuple[list[SemanticCluster], list[ExceptionEdge]]:
    """Build try + handler clusters and exception edge for one trap."""
    etype = short_class(trap["type"])

    try_bids = blocks_for_cluster(cluster_assignment, ClusterRole.TRY, trap_index)
    handler_bids = blocks_for_cluster(cluster_assignment, ClusterRole.HANDLER, trap_index)

    try_nids = [nid for bid in try_bids for nid in bid_to_nids.get(bid, [])]
    handler_nids = [nid for bid in handler_bids for nid in bid_to_nids.get(bid, [])]

    try_cluster: SemanticCluster = {
        "trapType": etype,
        "role": ClusterRole.TRY,
        "nodeIds": try_nids,
    }

    handler_cluster: SemanticCluster = {
        "trapType": etype,
        "role": ClusterRole.HANDLER,
        "nodeIds": handler_nids,
    }
    handler_entry_nid = block_first.get(trap["handler"], "")
    if handler_entry_nid:
        handler_cluster["entryNodeId"] = handler_entry_nid

    clusters = [try_cluster, handler_cluster]

    # Exception edge: try entry → handler entry
    exception_edges: list[ExceptionEdge] = []
    if handler_entry_nid:
        src_nid = (
            block_first.get(try_bids[0], "")
            if try_bids
            else next(
                (
                    block_first[cb]
                    for cb in trap.get("coveredBlocks", [])
                    if cb in block_first
                ),
                "",
            )
        )
        if src_nid:
            exception_edges.append(
                {
                    "from": src_nid,
                    "to": handler_entry_nid,
                    "trapType": etype,
                    "fromCluster": cluster_offset,
                    "toCluster": cluster_offset + 1,
                }
            )

    return (clusters, exception_edges)


def _build_clusters(
    traps: list[RawTrap],
    cluster_assignment: dict[BlockId, ClusterAssignment],
    bid_to_nids: dict[BlockId, list[NodeId]],
    block_first: dict[BlockId, NodeId],
) -> _ClusterBuildResult:
    """Build all clusters and exception edges from traps."""
    trap_results = [
        _build_trap_clusters(i, trap, cluster_assignment, bid_to_nids, block_first, i * 2)
        for i, trap in enumerate(traps)
    ]
    all_clusters = [c for clusters, _ in trap_results for c in clusters]
    all_exception_edges = [e for _, edges in trap_results for e in edges]
    return {"clusters": all_clusters, "exception_edges": all_exception_edges}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/test_build_semantic_graph.py::TestBuildClusters tests/test_build_semantic_graph.py::TestBuildSemanticGraphPass -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_semantic.py python/tests/test_build_semantic_graph.py
git commit -m "refactor: extract _build_clusters from build_semantic_graph_pass"
```

---

### Task 7: Rewire orchestrator and apply constants

**Files:**
- Modify: `python/ftrace_semantic.py:261-516` (the orchestrator)

- [ ] **Step 1: Rewrite `build_semantic_graph_pass` to use extracted functions and constants**

Replace the body of `build_semantic_graph_pass` (lines 271-516) with:

```python
def build_semantic_graph_pass(tree: MethodCFG, next_id: int = 0) -> MethodSemanticCFG:
    """Pass 4: Build semantic graph from enriched tree. Returns new tree.

    Consumes blocks, traps, mergedStmts, clusterAssignment, blockAliases.
    Emits nodes, edges, clusters, exceptionEdges. Drops raw fields.

    next_id: starting node ID counter (for unique IDs across the tree).
    Returns the transformed tree. The caller can read the highest node ID
    from the nodes to continue numbering for children.
    """
    if _is_leaf_node(tree):
        return dict(tree)

    # sourceTrace fallback — no blocks, just a linear list of lines
    tree_metadata = tree.get(_F_METADATA, {})
    if _F_MERGED_SOURCE_TRACE in tree_metadata and _F_BLOCKS not in tree:
        merged = tree_metadata[_F_MERGED_SOURCE_TRACE]
        all_nodes: list[SemanticNode] = [
            {
                "id": f"n{next_id + i}",
                "lines": [entry["line"]],
                "kind": classify_node_kind(entry),
                "label": make_node_label(entry),
            }
            for i, entry in enumerate(merged)
        ]
        all_edges: list[SemanticEdge] = [
            {"from": all_nodes[i]["id"], "to": all_nodes[i + 1]["id"]}
            for i in range(len(all_nodes) - 1)
        ]
        node_counter = next_id + len(all_nodes)

        drop_fields = {_F_SOURCE_TRACE, _F_METADATA}
        result = {
            k: v for k, v in tree.items() if k not in drop_fields and k != _F_CHILDREN
        }
        result["nodes"] = all_nodes
        result["edges"] = all_edges
        result["clusters"] = []
        result["exceptionEdges"] = []
        if all_nodes:
            result["entryNodeId"] = all_nodes[0]["id"]
        if _F_CHILDREN in tree:
            result[_F_CHILDREN] = [
                build_semantic_graph_pass(child, node_counter + i * 100)
                for i, child in enumerate(tree[_F_CHILDREN])
            ]
        return result

    # Main path: resolve → nodes → edges → clusters → assemble
    inputs = _resolve_inputs(tree, tree_metadata)
    node_result = _build_nodes(inputs["blocks"], inputs["block_aliases"], next_id)
    edge_result = _build_edges(
        inputs["edges"],
        node_result["block_first"],
        node_result["block_last"],
        node_result["bid_to_nids"],
        inputs["block_aliases"],
    )
    cluster_result = _build_clusters(
        inputs["traps"],
        inputs["cluster_assignment"],
        node_result["bid_to_nids"],
        node_result["block_first"],
    )

    # Assemble result: drop raw/intermediate fields, add semantic fields
    drop_fields = {_F_BLOCKS, _F_EDGES, _F_TRAPS, _F_METADATA, _F_SOURCE_TRACE}
    result = {k: v for k, v in tree.items() if k not in drop_fields and k != _F_CHILDREN}
    result["nodes"] = node_result["nodes"]
    result["edges"] = edge_result["edges"]
    result["clusters"] = cluster_result["clusters"]
    result["exceptionEdges"] = cluster_result["exception_edges"]

    if node_result["nodes"]:
        result["entryNodeId"] = node_result["nodes"][0]["id"]

    if _F_CHILDREN in tree:
        result[_F_CHILDREN] = [
            build_semantic_graph_pass(child, node_result["node_counter"] + i * 100)
            for i, child in enumerate(tree[_F_CHILDREN])
        ]

    return result
```

- [ ] **Step 2: Run all tests**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 3: Run E2E tests**

Run: `cd /Users/asgupta/code/java-bytecode-tools/test-fixtures && bash run-e2e.sh`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add python/ftrace_semantic.py
git commit -m "refactor: rewire build_semantic_graph_pass to use extracted functions"
```

---

### Task 8: Delete dead code from orchestrator

**Files:**
- Modify: `python/ftrace_semantic.py`

- [ ] **Step 1: Verify the old inline code in `build_semantic_graph_pass` is fully replaced**

The original lines 314-488 (variable declarations, for-loops, inline import) should now be gone, replaced by the calls to `_resolve_inputs`, `_build_nodes`, `_build_edges`, `_build_clusters`. If Task 7 was applied as a full replacement, this is already done. Verify by reading the function and confirming no orphaned code remains.

- [ ] **Step 2: Remove any unused imports**

Check if `RawStmt`, `SourceTraceEntry`, or `MergedStmt` are still used. If `MergedStmt` is only used in the type alias for `_process_block_stmts` parameter, keep it. Remove any imports that are no longer referenced.

- [ ] **Step 3: Run all tests**

Run: `cd /Users/asgupta/code/java-bytecode-tools/python && uv run python -m pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 4: Run E2E tests**

Run: `cd /Users/asgupta/code/java-bytecode-tools/test-fixtures && bash run-e2e.sh`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add python/ftrace_semantic.py
git commit -m "refactor: remove dead code after build_semantic_graph_pass decomposition"
```
