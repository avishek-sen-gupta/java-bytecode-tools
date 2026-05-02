# Inter-Procedural DDG Edge Generation

## Goal

Move PARAM and RETURN edge generation from `BwdSliceBuilder` (on-the-fly during slicing) into `DdgInterCfgArtifactBuilder` (pre-computed in the DDG artifact). The DDG becomes a self-contained inter-procedural data flow graph. The slicer simplifies to pure backward edge traversal.

## Current State

- `DdgInterCfgArtifactBuilder` reads the `calls` list from input but uses it only to build `CalltreeGraph`. Per-method DDG construction produces only LOCAL edges (intra-method reaching-definition). `FieldDepEnricher` adds HEAP edges. No PARAM or RETURN edges exist in the DDG.
- `BwdSliceBuilder` generates PARAM/RETURN edges on-the-fly during slicing (lines 52-86) using `callerIndex` built from calltree edges. This logic includes argument extraction, parameter index matching, and return value tracking.
- `ParamEdge` and `ReturnEdge` types already exist in the artifact package but are never emitted into the DDG.

## Design

### 1. New class: `InterProcEdgeBuilder`

**Responsibility:** Given all DDG nodes, all LOCAL edges, and the `calls` list, emit PARAM and RETURN edges.

**Input:** `List<DdgNode> nodes`, `List<DdgEdge> localEdges`, `List<Map<String, Object>> calls`

**Output:** `List<DdgEdge>` (PARAM + RETURN edges only)

#### PARAM edges (argument-index-precise)

For each call `{from: callerSig, to: calleeSig}`:

1. Find call-site nodes in caller: nodes where `method == callerSig` and `call.get("targetMethodSignature") == calleeSig` and `kind` is `ASSIGN_INVOKE` or `INVOKE`.
2. Find IDENTITY nodes in callee: nodes where `method == calleeSig` and `stmt` contains `@parameterN`. Extract N.
3. For each call-site node, parse the argument list from the Jimple stmt text. Pattern: `>\(([^)]*)\)$` extracts the args after the method signature reference. Split by `, ` for positional arg names.
4. For parameter index N, get `argN = argList[N]`. If N is out of bounds or argN is a constant/keyword, skip.
5. Find the reaching-def of argN at the call site: scan LOCAL edges where `to == callSiteNode.id`, find the edge whose `from` node's stmt assigns to argN (starts with `argN = ` or `argN := `).
6. Emit `DdgEdge(reachingDefNode.id, identityNode.id, new ParamEdge())`.

**Skipped cases (no PARAM edge emitted):**
- Constant arguments (`null`, `0`, `"string"`, `true`, `false`) — no reaching-def node
- `@this` identity nodes — receiver aliasing is handled by `FieldDepEnricher`
- Argument index out of bounds

#### RETURN edges

For each call `{from: callerSig, to: calleeSig}`:

1. Find RETURN nodes in callee: nodes where `method == calleeSig` and `kind == RETURN`.
2. Find ASSIGN_INVOKE nodes in caller calling calleeSig: nodes where `method == callerSig` and `kind == ASSIGN_INVOKE` and `call.get("targetMethodSignature") == calleeSig`.
3. For each `(returnNode, assignInvokeNode)` pair, emit `DdgEdge(returnNode.id, assignInvokeNode.id, new ReturnEdge())`.

**Skipped cases:**
- INVOKE (void call) call sites — no return value to track
- Callee has no RETURN nodes (void methods, or methods not in scope)

### 2. Integration in `DdgInterCfgArtifactBuilder`

After building per-method LOCAL edges and before enrichment:

```
LOCAL edges (per-method) → InterProcEdgeBuilder (PARAM + RETURN) → FieldDepEnricher (HEAP)
```

The `InterProcEdgeBuilder` is called between LOCAL edge construction and enrichment. The resulting edges are appended to `ddgEdges`.

### 3. Simplify `BwdSliceBuilder`

- `incomingEdges()`: remove the `instanceof LocalEdge || instanceof HeapEdge` filter — accept all edge types.
- Add `ReturnEdge` case in local-var extraction: use `extractReturnedLocal()` for RETURN edges (since `return x` has no LHS assignment).
- Remove on-the-fly PARAM generation (lines 52-69).
- Remove on-the-fly RETURN generation (lines 71-86).
- Remove `callerIndex` and `buildCallerIndex()` — no longer needed.

### 4. Edge direction conventions

All DDG edges follow `from = producer, to = consumer`:

| Edge type | from | to |
|-----------|------|----|
| LOCAL | reaching-def node | use node |
| HEAP | field-write node | field-read node |
| PARAM | reaching-def of argN in caller | `@parameterN` IDENTITY in callee |
| RETURN | RETURN node in callee | ASSIGN_INVOKE node in caller |

Backward slicing follows edges in reverse: for node N, find edges where `to == N.id`, trace `from`.

## Testing

- **Unit tests for `InterProcEdgeBuilder`**: construct DDG nodes and LOCAL edges manually, verify correct PARAM/RETURN edges are emitted. Test: single call, multiple calls to same callee, constant args (skipped), void calls (no RETURN edge), multiple return points.
- **Unit tests for updated `BwdSliceBuilder`**: verify backward slice traverses pre-computed PARAM/RETURN edges correctly. Verify removed on-the-fly logic doesn't regress.
- **Integration test in `DdgInterCfgArtifactBuilderTest`**: build DDG from a fixture with caller→callee, verify PARAM and RETURN edges appear in the artifact.
- **E2E test**: extend or add shell test verifying `ddg-inter-cfg | bwd-slice` traces across method boundaries.

## Out of scope

- `@this` / receiver wiring (handled by `FieldDepEnricher` via heap aliasing)
- Inter-procedural edges for methods outside the calltree scope
- Heap data flow through collections (Map.put/get) — separate concern
