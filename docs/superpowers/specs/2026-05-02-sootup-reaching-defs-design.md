# Replace Hand-Rolled Reaching-Def and Stmt Classification with SootUp APIs

**Date:** 2026-05-02
**Scope:** `DdgInterCfgMethodGraphBuilder.java`
**Goal:** Eliminate all regex-based string parsing by using SootUp's `ReachingDefs` analysis and structured `Stmt` type hierarchy.

## Problem

`DdgInterCfgMethodGraphBuilder.buildDdgEdges()` uses a single-pass linear walk over sorted basic blocks to compute reaching definitions. This fails when a def and its use span non-adjacent basic blocks (e.g., in methods with try-catch or complex control flow). The bug manifests as missing LOCAL edges — the backward slice stops short.

Additionally, `classifyStmt()` uses fragile regex matching on stringified Jimple to classify statements, when SootUp provides a structured `Stmt` type hierarchy for exactly this purpose.

## Solution

Two independent changes, delivered as separate commits:

### Change 1: Replace `buildDdgEdges` with SootUp `ReachingDefs`

**Delete:**
- `ASSIGN_LOCAL`, `IDENTITY_LOCAL`, `RETURN_VAL` regex patterns
- `extractUsedLocals()` method
- `extractLocalsFromExpr()` method
- `isJimpleKeyword()` method
- Current `buildDdgEdges()` body

**Replace with:** ~10 lines using `ReachingDefs`:

```java
private List<DdgEdge> buildDdgEdges(Body body, Map<Stmt, String> stmtToLocalId, String methodSig) {
    ReachingDefs rd = new ReachingDefs(body.getStmtGraph());
    Map<Stmt, List<Stmt>> defsByUse = rd.getReachingDefs();
    List<DdgEdge> edges = new ArrayList<>();
    for (var entry : defsByUse.entrySet()) {
        String toId = methodSig + "#" + stmtToLocalId.get(entry.getKey());
        for (Stmt defStmt : entry.getValue()) {
            String fromId = methodSig + "#" + stmtToLocalId.get(defStmt);
            edges.add(new DdgEdge(fromId, toId, new LocalEdge()));
        }
    }
    return edges;
}
```

**Net effect:** ~80 lines deleted, ~10 lines added. Fixed-point analysis handles cross-block defs correctly.

### Change 2: Replace `classifyStmt` regex with SootUp `Stmt` types

**Delete:** Current `classifyStmt()` body with string matching.

**Replace with:** `instanceof` checks on SootUp types:

```java
private StmtKind classifyStmt(Stmt stmt) {
    if (stmt instanceof JIdentityStmt) return StmtKind.IDENTITY;
    if (stmt instanceof JReturnStmt) return StmtKind.RETURN;
    if (stmt instanceof JAssignStmt assign && assign.containsInvokeExpr())
        return StmtKind.ASSIGN_INVOKE;
    if (stmt instanceof JInvokeStmt) return StmtKind.INVOKE;
    return StmtKind.ASSIGN;
}
```

**Net effect:** ~10 lines of regex replaced with ~6 lines of type checks. No more string-matching fragility.

## Downstream Impact

Both changes are safe for downstream consumers:

- **`BwdSliceBuilder`**: Treats LOCAL edges generically. More edges means more complete slices.
- **`InterProcEdgeBuilder.findReachingDefId()`**: Filters by `instanceof LocalEdge` and checks if source stmt starts with `argLocal + " = "` or `argLocal + " := "`. Naturally ignores non-matching sources — safe with additional LOCAL edges.
- **`classifyStmt` consumers**: `DdgNode.kind()` is used by `InterProcEdgeBuilder` to find IDENTITY, ASSIGN_INVOKE, INVOKE, and RETURN nodes. The SootUp type checks produce identical classification for all statement types that matter.

## Edge Cases

- **`ReachingDefs` returns defs for stmts not in `stmtToLocalId`:** Cannot happen — both iterate `body.getStmtGraph().getNodes()`.
- **More LOCAL edges than before:** Expected and desired. The single-pass analysis was under-approximating. More edges = more complete dependency tracking.
- **`JReturnVoidStmt`:** Falls through to `StmtKind.ASSIGN` in `classifyStmt`. This matches current behavior (void returns don't match `"^return \\w+"` regex either). These stmts carry no data dependency.

## Testing Strategy

- **Red test first (Change 1):** Write a test that asserts a LOCAL edge exists between a def and use spanning non-adjacent basic blocks (the `VarReassignService.sanitize` method). This test fails with current single-pass analysis, passes with `ReachingDefs`.
- **Behavioral equivalence (Change 2):** Write a test that asserts `classifyStmt` produces the same `StmtKind` for every stmt in a fixture method, comparing old regex approach vs new type-check approach. Then delete old approach.
- **E2E:** Full `run-e2e.sh` must pass. Re-run real-world pipeline to verify chain now reaches the target `new HashMap` allocation.
