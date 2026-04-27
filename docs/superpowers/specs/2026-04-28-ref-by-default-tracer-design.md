# Ref-by-Default Call Tree Tracer

## Problem

The current `ForwardTracer` arbitrarily expands the first encounter of each method inline and creates ref stubs for subsequent encounters. Which methods get expanded is a side effect of DFS traversal order — not a deliberate user choice. This couples discovery, CFG construction, and tree assembly in a single recursive walk, with `globalVisited` doing double duty as both an infinite-recursion guard and an inline-vs-ref decision.

## Design

Replace the single-pass recursive tracer with a two-pass architecture where every method (except the root) is a ref by default. Expansion becomes a deliberate user-controlled choice via the existing `ftrace_expand_refs.py` tool.

### Two-Pass Architecture

**Pass 1 — Discover** (pure call graph traversal, no bytecode)

- Input: root method signature, prebuilt call graph, filter.
- DFS over the call graph from the root.
- `pathAncestors` detects cycles; `visited` prevents re-visiting.
- Each reachable method is classified: `NORMAL`, `CYCLE`, or `FILTERED`.
- Output: `DiscoveryResult` — classification map plus callee lists (with call-site line numbers) per method.

**Pass 2 — Build** (flat loop, no recursion)

- Input: `DiscoveryResult` + SootUp method bodies.
- For each `NORMAL` method: call existing `buildBlockTrace` to construct blocks/edges/traps. Children are ref nodes pointing to other discovered methods.
- `CYCLE` → stub node with `"cycle": true`.
- `FILTERED` → stub node with `"filtered": true`.
- No recursion. No `globalVisited`. Each method's CFG is built in complete isolation.
- Output: root trace (expanded) + refIndex (all other NORMAL methods).

```
Root Signature
     │
     ▼
┌────────────┐     ┌────────────┐
│ Call Graph  │────▶│  Pass 1    │──▶ DiscoveryResult
│ (prebuilt)  │     │  Discover  │    {classifications, callees}
└────────────┘     └────────────┘
                         │
                         ▼
                   ┌────────────┐
                   │  Pass 2    │──▶ SlicedTrace
                   │  Build     │    {trace, refIndex}
                   └────────────┘
```

`globalVisited` is eliminated — it was an artifact of doing discovery and building in one pass.

### Output Format

Root method is expanded (blocks/edges/traps inline). All children at every level are ref nodes. The refIndex holds every other method's full MethodCFG, and those entries themselves have ref children. The entire call graph is navigable by following refs through the index.

```json
{
  "trace": {
    "class": "Svc", "method": "run",
    "blocks": [...], "edges": [...], "traps": [...],
    "children": [
      {"class": "Foo", "method": "bar", "ref": true, "methodSignature": "void Foo.bar()"},
      {"class": "Foo", "method": "bar", "ref": true, "methodSignature": "void Foo.bar()"}
    ]
  },
  "refIndex": {
    "void Foo.bar()": {
      "class": "Foo", "method": "bar",
      "blocks": [...], "edges": [...], "traps": [...],
      "children": [
        {"class": "Baz", "method": "qux", "ref": true, "methodSignature": "void Baz.qux()"}
      ]
    },
    "void Baz.qux()": { "..." }
  }
}
```

Key properties:

- One ref per call site (two calls to `Foo.bar` = two ref nodes, not deduplicated).
- Cycle and filtered nodes remain as leaf stubs with their respective flags. No entries in refIndex for these.
- `callSiteLine` is still attached to each ref child.

### Changes Required

**Java side (ForwardTracer.java):**

1. New `DiscoveryResult` record — holds classification map and callee map.
2. New `discoverReachable()` method — DFS over call graph with `pathAncestors` + `visited`.
3. Modify `traceForward()` — calls discover then build sequentially.
4. `buildForwardNode` becomes `buildMethodCFG` — no longer recursive. Builds one method's CFG, attaches ref children from discovery result. Called in a flat loop.
5. `globalVisited` field deleted.

**Python side:**

No changes. `ftrace_expand_refs.py` already expands refs from refIndex. The 4-pass semantic graph pipeline already handles ref leaf nodes as pass-through copies.

**E2E tests:**

Existing E2E fixtures need updated expected output — children that were previously expanded will now be refs. The data is the same, just moved from inline to refIndex.

### What Stays the Same

- `buildBlockTrace` (lines 181-402) — CFG construction for a single method. Untouched.
- Call graph loading — still prebuilt, passed into pass 1.
- Cycle/filtered stub nodes — same shape, same flags.
- `callSiteLine` — still attached to each ref child.
- `ftrace_expand_refs.py` — works as-is.
- 4-pass semantic graph pipeline — no changes.
- `--collapse` in xtrace — unrelated feature. Untouched.

### Java Design Constraints

All new Java code in this feature follows these constraints:

1. **Eliminate magic strings and numbers.** JSON field names (`"ref"`, `"cycle"`, `"methodSignature"`, etc.) are `static final String` constants. Numeric thresholds are named constants. No inline literals in logic.

2. **Prefer small composable functions.** Each function does one thing and returns a value. The current `buildForwardNode` (75 lines, CC ~8) decomposes into 4-5 focused methods each under CC ~3. Guard clauses at the top, happy path outside conditions.

3. **Strongly typed domain classes.** No `Map<String, Object>` or `JsonObject` at internal boundaries. New domain types:
   - `Classification` enum: `NORMAL`, `CYCLE`, `FILTERED`
   - `DiscoveryResult` record: classification map + callee map
   - `CallSite` record: callee signature + call-site line number
   - `MethodCFG` record (or strengthen existing): blocks, edges, traps, children
   - Generics over raw types everywhere (`List<CallSite>` not `List`)

4. **Granular unit tests.** Each new function gets its own test class. Pass 1 discovery tests are independent of pass 2 build tests. Tests assert specific values, not just non-null.

5. **TDD.** Tests written first, seen to fail, then implementation. No exceptions.

Existing code outside the change scope is left as-is.
