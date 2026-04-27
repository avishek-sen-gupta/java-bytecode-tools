# Extract RawBlockEdge from RawBlock.successors

## Context

`RawBlock.successors` is `list[str]` — block IDs of successor blocks embedded in each block as an adjacency list. Branch semantics (T/F) are encoded implicitly by position: `successors[0]` = true, `successors[1]` = false. This positional encoding is fragile and prevents lifting edges to a top-level list.

This refactoring introduces `RawBlockEdge` as a typed edge object and moves edges from per-block `successors` to a top-level `edges` field on `MethodCFG`, mirroring how `MethodSemanticCFG` already represents its semantic graph as top-level `nodes` + `edges`.

## Design

### New type: `RawBlockEdge`

```python
_RawBlockEdgeRequired = TypedDict("_RawBlockEdgeRequired", {
    "fromBlock": str,
    "toBlock": str,
})

class RawBlockEdge(_RawBlockEdgeRequired, total=False):
    label: str  # "T", "F", or absent for unconditional edges
```

`branchCondition` stays on `RawBlock` — it describes the condition text (e.g. `"i <= 0"`), a property of the branch node. The edge `label` carries which branch arm it represents.

### Changes by file

**`python/ftrace_types.py`:**
- Add `RawBlockEdge` TypedDict
- Add `edges: list[RawBlockEdge]` to `MethodCFG`
- Remove `successors: list[str]` from `RawBlock`

**`java/.../ForwardTracer.java`:**
- Build a top-level `edges` list on the method instead of per-block `successors`
- For branch blocks with 2 successors: emit edges with `label: "T"` / `label: "F"`
- For non-branch blocks: emit edges without `label`
- Stop emitting `successors` on individual blocks

**`python/ftrace_semantic.py` (pass 4):**
- Build adjacency map from `MethodCFG.edges` keyed by `fromBlock`
- Use `label` field directly for T/F instead of positional inference
- Remove `block.get("successors", [])` iteration

**Tests:**
- Update all test fixtures: replace `successors` on blocks with `edges` on method dicts
- E2E tests validate full Java-to-Python pipeline

### Files not changed

- `ftrace_to_dot.py` — consumes `MethodSemanticCFG`, not `MethodCFG`
- `ftrace_slice.py` — does not read `successors`
- `ftrace_expand_refs.py` — does not read `successors`

## Scope

Light refactoring. Single structural change across Java producer and Python consumer, following existing patterns.
