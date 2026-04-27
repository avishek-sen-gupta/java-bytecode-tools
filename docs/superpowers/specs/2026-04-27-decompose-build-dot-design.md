# Decompose build_dot

## Context

`build_dot` in `python/ftrace_to_dot.py` (lines 107-233) is a 127-line function with a nested 102-line `add_method` that mutates three outer variables (`lines`, `cross_edges`, `cluster_counter`). It is the DOT rendering pass, consuming `MethodSemanticCFG` and producing a Graphviz DOT string.

Beads issue: `java-bytecode-tools-351`.

## Approach

**Approach A: Return-and-concatenate.** Extract helpers that return DOT line lists. The recursive `_render_method` threads a counter and returns `_MethodDotResult`. The orchestrator (`build_dot`) becomes a thin wrapper: header + render + cross_edges + footer.

Key property: `_render_trap_cluster` and `_render_cross_edges` are independent — neither consumes from the other, both consume from the node/edge data in the method.

## Internal TypedDicts

Module-private, not exported. Used only as the return type for `_render_method`.

```python
class _MethodDotResult(TypedDict):
    lines: list[str]          # DOT lines for this method + descendants
    cross_edges: list[str]    # parent→child call edges
    next_counter: int         # updated counter for unique IDs
```

## Extracted Functions

### `_render_leaf(node, counter) → tuple[list[str], int]`

Handles ref/cycle/filtered leaf nodes. Returns DOT lines for a single leaf node and updated counter. Pure — no access to outer state.

### `_render_trap_cluster(index, cluster, bid_to_nids_fn) → list[str]`

Renders one trap cluster as a DOT subgraph with try/handler regions. No counter needed — cluster IDs come from the trap index. Pure.

### `_render_cross_edges(nodes, children, child_entries, entry_nid) → list[str]`

Builds parent→child call edges by matching `callSiteLine` in child methods to node lines in the parent. Returns DOT edge lines. Pure.

### `_render_method(node, counter) → _MethodDotResult`

Main recursive function. For each method:
1. If leaf → delegate to `_render_leaf`, return early.
2. Render subgraph header with `counter` as cluster ID.
3. Render nodes via comprehension over `_render_node`.
4. Render edges via comprehension over `_render_edge`.
5. Render trap clusters via comprehension over `_render_trap_cluster`.
6. Render exception edges via comprehension over `_render_exception_edge`.
7. Recurse into children, threading counter through with `reduce`.
8. Render cross edges via `_render_cross_edges`.
9. Return `_MethodDotResult` with all lines, cross_edges, and final counter.

### `build_dot(root) → str`

Thin orchestrator:

```python
def build_dot(root: MethodSemanticCFG) -> str:
    header = [
        "digraph ftrace {", "  rankdir=TB;", "  compound=true;",
        '  node [shape=box, ...];', '  edge [...];', "",
    ]
    result = _render_method(root, 0)
    footer = ["  // Cross-cluster call edges", *result["cross_edges"], "}"]
    return "\n".join([*header, *result["lines"], *footer])
```

## Constraints

- No `for` loops with mutation — comprehensions, `map`, `filter`, `reduce`.
- No mutable outer state — counter threaded as argument/return, no `[0]` hack.
- `frozenset` where applicable for immutable collections.
- All `.get()` calls provide concrete defaults (`""`, `[]`, `{}`).
- Existing constants (`NODE_STYLE`, `BRANCH_COLORS`) are sufficient; no new constants needed.

## Test Strategy

- Each extracted function (`_render_leaf`, `_render_trap_cluster`, `_render_cross_edges`) gets its own test class with unit tests.
- Existing 17 integration tests remain unchanged as integration tests (same inputs, same outputs).
- `_render_method` tested indirectly through `build_dot` integration tests.

## Files Modified

1. `python/ftrace_to_dot.py` — extract functions, add TypedDict, refactor `build_dot` to orchestrator
2. `python/tests/test_dot_rendering.py` — add unit test classes for each extracted function

## Files NOT Modified

- `python/ftrace_semantic.py` — produces `MethodSemanticCFG`, unaffected
- `python/ftrace_types.py` — no type changes needed
- Other pipeline modules — don't touch DOT rendering
