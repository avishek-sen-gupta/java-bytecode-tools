# Semantic Graph Pipeline Design

## Problem

`ftrace_to_dot.py` mixes graph transformations (merging, clustering, dedup, edge suppression) with DOT rendering. This makes the code hard to test, hard to extend, and violates separation of concerns. The Python layer should be a dumb renderer; all graph logic should be explicit, composable pipeline stages.

## Architecture

A Unix-composable pipeline of four tools, each defaulting to stdout:

```
xtrace (Java)
  │  Raw block graph JSON (unchanged)
  ▼
ftrace-slice (Python, optional, unchanged)
  │  Subtree extraction on raw JSON
  ▼
ftrace-semantic (Python, new)
  │  Four incremental passes: raw → semantic JSON
  ▼
ftrace-to-dot (Python, rewritten)
  │  Dumb renderer: semantic JSON → DOT/SVG/PNG
  ▼
Output
```

All Python tools: `--input file` for file input, `--output file` for file output. Omitting `--output` writes to stdout.

Example pipelines:

```bash
# Full pipeline with slice
ftrace-slice --input raw.json --query '...' | ftrace-semantic | ftrace-to-dot > graph.dot

# Skip slice
ftrace-semantic --input raw.json | ftrace-to-dot --output graph.svg
```

## Semantic transform: four passes

Each pass is a pure function `dict → dict`. No mutation of input. Composed as:

```python
pipe(merge_stmts, assign_clusters, deduplicate_blocks, build_semantic_graph)(root)
```

Leaf nodes (ref, cycle, filtered) pass through all stages unchanged.

### Pass 1: `merge_stmts`

Deduplicates each block's `stmts` by line number, aggregating calls/branches/assigns. Adds `mergedStmts` to each block. Preserves raw `stmts`.

Input block:
```json
{"id": "B2", "stmts": [
  {"line": 9, "call": "RuntimeException.<init>"},
  {"line": 9}
], "successors": ["B3"]}
```

Output block:
```json
{"id": "B2", "stmts": [...], "mergedStmts": [
  {"line": 9, "calls": ["RuntimeException.<init>"], "branches": [], "assigns": []}
], "successors": ["B3"]}
```

### Pass 2: `assign_clusters`

Computes cluster assignment for each block based on trap data. Handler membership takes priority over coverage. Adds `clusterAssignment` to each method node.

```json
{
  "clusterAssignment": {
    "B0": {"kind": "try", "trapIndex": 0},
    "B5": {"kind": "handler", "trapIndex": 0}
  }
}
```

### Pass 3: `deduplicate_blocks`

Within each cluster, computes content signatures from `mergedStmts` + `branchCondition`. Blocks with identical signatures alias to a canonical block. Adds `blockAliases` to each method node.

```json
{
  "blockAliases": {"B8": "B3", "B10": "B5"}
}
```

### Pass 4: `build_semantic_graph`

Consumes all intermediate fields and emits the final semantic representation. Drops `blocks`, `traps`, `mergedStmts`, `clusterAssignment`, `blockAliases`. Preserves tree structure (`children`, `class`, `method`, `lineStart`, `lineEnd`, `callSiteLine`, etc.).

Output per method node:

```json
{
  "nodes": [
    {"id": "n0", "lines": [6], "kind": "plain", "label": ["L6"]},
    {"id": "n1", "lines": [6], "kind": "branch", "label": ["L6", "i <= 0"]},
    {"id": "n2", "lines": [9], "kind": "call", "label": ["L9", "RuntimeException.<init>"]}
  ],
  "edges": [
    {"from": "n0", "to": "n1"},
    {"from": "n1", "to": "n2", "branch": "F"},
    {"from": "n1", "to": "n3", "branch": "T"}
  ],
  "clusters": [
    {"trapType": "RuntimeException", "role": "try", "nodeIds": ["n0", "n1", "n2"]},
    {"trapType": "RuntimeException", "role": "handler", "nodeIds": ["n5", "n6"],
     "entryNodeId": "n5"}
  ],
  "exceptionEdges": [
    {"from": "n1", "to": "n5", "trapType": "RuntimeException",
     "fromCluster": 0, "toCluster": 1}
  ]
}
```

Node `kind` values: `plain`, `call`, `branch`, `assign`, `cycle`, `ref`, `filtered`.

Edge dedup, self-loop suppression, and reverse-edge suppression (shared-node logic) are handled here.

## Rewritten `ftrace-to-dot`

A dumb renderer. Reads semantic JSON, produces DOT. Only visual decisions:

### Node styling

| `kind`     | shape   | fillcolor         | style                  |
|------------|---------|-------------------|------------------------|
| `plain`    | box     | white             | filled,rounded         |
| `call`     | box     | #d4edda (green)   | filled,rounded         |
| `branch`   | diamond | #cce5ff (blue)    | filled                 |
| `assign`   | box     | #f5f5dc (beige)   | filled,rounded         |
| `cycle`    | box     | #ffcccc (red)     | filled,rounded,dashed  |
| `ref`      | box     | #e8e8e8 (grey)    | filled,rounded,dashed  |
| `filtered` | box     | #fff3cd (yellow)  | filled,rounded,dashed  |

### Edge styling

| Type             | Color   | Style  | Label          |
|------------------|---------|--------|----------------|
| Normal           | black   | solid  | none           |
| Branch T         | #28a745 | solid  | "T"            |
| Branch F         | #dc3545 | solid  | "F"            |
| Exception        | #ffa500 | dashed | trap type name |
| Cross-cluster    | #e05050 | bold   | none           |

### Cluster styling

| Role      | Border color | Label format            |
|-----------|-------------|-------------------------|
| `try`     | #ffa500     | "try (ExceptionType)"   |
| `handler` | #007bff     | "finally" or "catch (X)"|

Method clusters: grey rounded filled box, label "Class.method [lineStart-lineEnd]".

The renderer iterates `nodes`, `edges`, `clusters`, `exceptionEdges` — no graph logic.

Target: ~100-120 lines.

## File structure

| File | Action | Description |
|------|--------|-------------|
| `python/ftrace_semantic.py` | New | Four passes + CLI |
| `python/ftrace_to_dot.py` | Rewrite | Dumb semantic JSON → DOT renderer |
| `python/ftrace_slice.py` | Minor | Ensure stdout default when no `--output` |
| `python/pyproject.toml` | Update | Register `ftrace-semantic` entry point |
| `python/tests/test_ftrace_semantic.py` | New | Unit tests per pass (TDD) |
| `python/tests/test_dot_rendering.py` | New | Renderer tests against semantic JSON (TDD) |
| `python/tests/test_dot_trap_clusters.py` | Update/remove | Existing tests adapted or replaced |
| `test-fixtures/tests/*` | Update | E2E tests run full pipeline |

## Design principles

### TDD

Every function is written test-first:
1. Write test for the function
2. Verify it fails (red)
3. Implement the function (green)
4. Refactor if needed

### Functional programming

- **No mutation**: Every pass returns a new dict. Input arguments are never modified.
- **Comprehensions over loops**: Use list/dict/set comprehensions, `map`, `filter`, `reduce` where readable.
- **Small pure functions**: Each function does one thing, takes explicit arguments, returns a value. No side effects.
- **Dependency injection**: Node ID generation is an injected counter/factory, not a closure over mutable state. No module-level mutable state.

## Semantic JSON schema summary

Method node (full):
```
class, method, methodSignature, lineStart, lineEnd, sourceLineCount,
callSiteLine?, children,
nodes, edges, clusters, exceptionEdges
```

Method node (leaf — ref/cycle/filtered):
```
class, method, methodSignature, callSiteLine?,
ref? | cycle? | filtered?
```

## Edge cases

| Case | Behavior |
|------|----------|
| No blocks (sourceTrace fallback) | `merge_stmts` uses `sourceTrace` instead, passes 2-3 no-op, pass 4 emits linear node chain |
| No traps | `assign_clusters` returns empty assignment, `deduplicate_blocks` skips clustering, pass 4 emits no clusters/exceptionEdges |
| Empty method | All passes no-op, single placeholder node emitted |
| Leaf nodes (ref/cycle/filtered) | All passes pass through unchanged |
| Block covered by multiple traps | Each trap's cluster is independent; handler wins |
| Nested try-catch-finally | Inner handler entries block gap-fill (handled by Java, upstream) |
