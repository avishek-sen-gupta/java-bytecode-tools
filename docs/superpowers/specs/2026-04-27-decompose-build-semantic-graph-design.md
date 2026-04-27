# Decompose build_semantic_graph_pass

## Context

`build_semantic_graph_pass` in `python/ftrace_semantic.py` (lines 261-516) is a 255-line function with 5 responsibilities and 12+ mutable local variables. It is pass 4 of the ftrace pipeline, consuming enriched `MethodCFG` and producing `MethodSemanticCFG`.

Beads issue: `java-bytecode-tools-bba`.

## Approach

**Approach B: 4 extracted functions + orchestrator.** Extract `_resolve_inputs`, `_build_nodes`, `_build_edges`, `_build_clusters` as pure functions. The sourceTrace fallback stays inline as an early-return path. The orchestrator calls resolve → nodes → edges → clusters → assemble.

Key property: edges and clusters are independent — both consume from the node-building output, neither consumes from the other.

## Field-Name Constants

Module-private constants for all raw-tree field names used in dict access:

```python
_F_BLOCKS = "blocks"
_F_EDGES = "edges"
_F_TRAPS = "traps"
_F_METADATA = "metadata"
_F_SOURCE_TRACE = "sourceTrace"
_F_CHILDREN = "children"
_F_MERGED_SOURCE_TRACE = "mergedSourceTrace"
_F_CLUSTER_ASSIGNMENT = "clusterAssignment"
_F_BLOCK_ALIASES = "blockAliases"
```

TypedDict key accesses on the internal result types do not need constants — those are type-checked.

## Type Aliases

Script-internal domain aliases for string IDs:

```python
BlockId = str
NodeId = str
```

## Internal TypedDicts

Module-private, not exported. Used only as return types for the extracted functions.

```python
class _ResolvedInput(TypedDict):
    blocks: list[RawBlock]
    edges: list[RawBlockEdge]
    traps: list[RawTrap]
    cluster_assignment: dict[BlockId, ClusterAssignment]
    block_aliases: dict[BlockId, BlockId]

class _NodeBuildResult(TypedDict):
    nodes: list[SemanticNode]
    block_first: dict[BlockId, NodeId]
    block_last: dict[BlockId, NodeId]
    bid_to_nids: dict[BlockId, list[NodeId]]
    node_counter: int

class _EdgeBuildResult(TypedDict):
    edges: list[SemanticEdge]

class _ClusterBuildResult(TypedDict):
    clusters: list[SemanticCluster]
    exception_edges: list[ExceptionEdge]
```

## Extracted Functions

### `_resolve_inputs(tree, tree_metadata) → _ResolvedInput`

Reads blocks, edges, traps, clusterAssignment, blockAliases from the tree and metadata dict. Pure extraction — normalizes access so builders never touch the raw tree. All `.get()` calls use concrete defaults (`[]`, `{}`).

### `_build_nodes(blocks, block_aliases, next_id) → _NodeBuildResult`

Currently lines 320-387. Takes blocks and aliases, produces all semantic nodes plus the three index maps and updated `node_counter`.

FP refactoring:
- Per-block logic becomes a function processing one block, returning its nodes and index entries.
- Outer loop becomes a `reduce` or fold that accumulates the `_NodeBuildResult`.
- No mutable `node_counter` threading — use positional computation or fold accumulator.

### `_build_edges(raw_edges, block_first, block_last, bid_to_nids, block_aliases) → _EdgeBuildResult`

Currently lines 389-432. Takes raw CFG edges and block→node index maps.

Two sub-concerns:
1. Intra-block edges (sequential within a block) — already a comprehension.
2. Inter-block edges (CFG connections) — currently uses mutable `emitted: set`. Refactor to use `frozenset` threaded through a `reduce`, or pre-compute dedup keys and filter.

Move `from collections import Counter` to module-level import.

### `_build_clusters(traps, cluster_assignment, bid_to_nids, block_first) → _ClusterBuildResult`

Currently lines 434-488. Takes traps, cluster assignment, and node index maps.

FP refactoring:
- Each trap produces a `(try_cluster, handler_cluster, exception_edge)` tuple.
- A comprehension over `enumerate(traps)` replaces the mutating loop.
- Unzip into the three output lists.

## Orchestrator Shape

```python
def build_semantic_graph_pass(tree: MethodCFG, next_id: int = 0) -> MethodSemanticCFG:
    if _is_leaf_node(tree):
        return dict(tree)

    # sourceTrace fallback (early return, stays inline)
    tree_metadata = tree.get(_F_METADATA, {})
    if _F_MERGED_SOURCE_TRACE in tree_metadata and _F_BLOCKS not in tree:
        ... # existing fallback logic, uses constants

    # Main path
    inputs = _resolve_inputs(tree, tree_metadata)
    node_result = _build_nodes(inputs["blocks"], inputs["block_aliases"], next_id)
    edge_result = _build_edges(
        inputs["edges"], node_result["block_first"],
        node_result["block_last"], node_result["bid_to_nids"],
        inputs["block_aliases"],
    )
    cluster_result = _build_clusters(
        inputs["traps"], inputs["cluster_assignment"],
        node_result["bid_to_nids"], node_result["block_first"],
    )

    # Assemble + recurse children (~15 lines, stays in orchestrator)
    ...
```

## Constraints

- All `.get()` calls provide concrete defaults: `""`, `[]`, `{}`, `False`. No implicit `None` fallback.
- `frozenset` over `set` for immutable collections.
- No `for` loops with mutation — comprehensions, `map`, `filter`, `reduce`.
- No inline imports — all imports at module top.
- Constants for all magic strings in raw-tree dict access.

## Test Strategy

- Each extracted function gets its own test class with unit tests.
- Existing `TestBuildSemanticGraphPass` tests remain unchanged as integration tests (same inputs, same outputs).
- No immutability tests — the functions are pure by construction (comprehensions, no mutation).

## Files Modified

1. `python/ftrace_semantic.py` — extract functions, add constants, add TypedDicts, refactor to FP
2. `python/tests/test_build_semantic_graph.py` — add unit test classes for each extracted function

## Files NOT Modified

- `python/ftrace_types.py` — internal types stay in `ftrace_semantic.py`
- `python/ftrace_to_dot.py` — consumes `MethodSemanticCFG`, unaffected
- Other pipeline modules — don't touch pass 4 internals
