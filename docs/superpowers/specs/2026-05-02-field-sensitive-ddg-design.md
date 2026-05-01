# Field-Sensitive DDG Design

## Goal

Extend `ddg-inter-cfg` with heap alias-aware field dependency edges using Qilin pointer analysis, so that `bwd-slice` can track data flow through object fields across method boundaries.

## Scope

### In scope

- Run Qilin PTA during `ddg-inter-cfg` construction on the same SootUp `View`
- Detect field read/write pairs that may-alias and emit `heap` edges in the DDG
- Restructure the `ddg-inter-cfg` artifact into two typed graph containers (`calltree`, `ddg`)
- Introduce a typed Java record hierarchy for the artifact
- Add `--unbounded` flag to widen field-write search beyond fw-calltree scope
- Propagate `metadata.root` from the fw-calltree artifact (entry point for Qilin)
- Update `bwd-slice` to follow `heap` edges in addition to `local` edges

### Out of scope

- Replacing SootUp's intraprocedural flow-sensitive dataflow
- Context-sensitive Qilin configurations (use Andersen's insensitive by default)
- Rendering or visualisation changes
- Modifying `fw-calltree` graph structure beyond adding `metadata`

## Artifact Schema

### fw-calltree artifact (modified)

Adds a `metadata` dict at the top level. All existing keys are untouched.

```json
{
  "metadata": { "root": "<com.example.app.OrderService: java.lang.String processOrder(int)>" },
  "nodes": { ... },
  "edges": [ ... ]
}
```

`metadata` is an open-ended `Map<String, String>`. Consumers that do not know about `metadata` ignore it safely. `ddg-inter-cfg` reads `metadata.root` (defaults to empty string if absent for backward compatibility).

### ddg-inter-cfg artifact (redesigned)

Two graph containers wrapped in a top-level object:

```json
{
  "metadata": { "root": "<sig>" },
  "calltree": {
    "nodes": [
      { "id": "<sig>", "className": "OrderService", "methodName": "processOrder" }
    ],
    "edges": [
      { "from": "<caller-sig>", "to": "<callee-sig>" }
    ]
  },
  "ddg": {
    "nodes": [
      { "id": "<sig>#s1", "method": "<sig>", "stmtId": "s1",
        "stmt": "i0 := @parameter0: int", "line": -1, "kind": "IDENTITY" }
    ],
    "edges": [
      { "from": "<sig>#s1", "to": "<sig>#s6", "edge_info": { "kind": "LOCAL" } },
      { "from": "<sigA>#s5", "to": "<sigB>#s2",
        "edge_info": { "kind": "HEAP", "field": "<com.example.app.Order: java.lang.String status>" } }
    ]
  }
}
```

Node IDs in `ddg.nodes` are globally unique compound keys: `"<methodSig>#<stmtId>"`. Intra-method and cross-method edges are structurally identical — no special list needed for cross-method cases.

`calltree.edges` replaces the former top-level `calls` list and is used by `bwd-slice` to build the caller index.

This is a **breaking schema change**. Existing `ddg-inter-cfg` artifacts on disk must be regenerated.

### Edge kinds

| kind | meaning |
|------|---------|
| `LOCAL` | intra-method def-use on a Jimple local (formerly `ddg`) |
| `HEAP` | field read/write pair connected via Qilin may-alias |
| `PARAM` | call site argument → callee parameter identity stmt |
| `RETURN` | callee return stmt → caller call site assignment |

## Typed Record Hierarchy

```java
record Artifact(Map<String, String> metadata, CalltreeGraph calltree, DdgGraph ddg) {}

record CalltreeGraph(List<CalltreeNode> nodes, List<CalltreeEdge> edges) {}
record CalltreeNode(String id, String className, String methodName) {}
record CalltreeEdge(String from, String to) {}

record DdgGraph(List<DdgNode> nodes, List<DdgEdge> edges) {}
record DdgNode(String id, String method, String stmtId, String stmt,
               int line, StmtKind kind, Map<String, String> call) {}
record DdgEdge(String from, String to, EdgeInfo edgeInfo) {}

enum StmtKind  { IDENTITY, ASSIGN_INVOKE, RETURN, INVOKE }
enum EdgeKind  { LOCAL, HEAP, PARAM, RETURN }

sealed interface EdgeInfo permits LocalEdge, HeapEdge, ParamEdge, ReturnEdge {}
record LocalEdge()             implements EdgeInfo {}
record HeapEdge(String field)  implements EdgeInfo {}
record ParamEdge()             implements EdgeInfo {}
record ReturnEdge()            implements EdgeInfo {}
```

`DdgNode.call` stays as `Map<String, String>` (contains `targetMethodSignature`). Method signatures stay as strings throughout — `MethodRef` parsing deferred.

Jackson with record support deserializes these with no annotations when field names match. The sealed `EdgeInfo` hierarchy needs a custom deserializer dispatching on `kind`.

## Architecture

### `FieldDepEnricher` (`tools.bytecode`)

Pure functional. Receives:
- The SootUp `View` (shared with `DdgInterCfgBuilder`)
- The Qilin `PTA` instance
- The built `DdgGraph` (nodes and local/param/return edges already populated)
- A `Set<String>` of in-scope method signatures

For each `DdgNode` where `stmt` matches a field read pattern `$local = obj.<C: T f>`:
1. Extract field signature `<C: T f>` and receiver local `obj`
2. Find all nodes in scope where `stmt` matches a field write `obj2.<C: T f> = val`
3. Call `AliasAssertion.isMayAlias(pta, obj, obj2)` in the context of their respective methods
4. For each aliasing pair, emit a `HeapEdge` from the write node ID to the read node ID

Returns an enriched `DdgGraph` with additional `heap` edges appended. Does not mutate the input graph.

### `DdgInterCfgCommand` (`tools.bytecode.cli`)

Adds:
```
--unbounded    Widen heap dependency search to all Qilin-reachable methods
               (default: fw-calltree scope only)
```

Bounded scope: `Set<String>` built from `calltree.nodes` IDs.
Unbounded scope: full Qilin reachable set from the root entry point.

Scope set is injected into `FieldDepEnricher` — the enricher itself has no mode awareness.

### `DdgInterCfgBuilder` (`tools.bytecode`)

Emits the new `Artifact` schema. After building DDG nodes and local/param/return edges, invokes `FieldDepEnricher` to append heap edges before serialisation.

### `BwdSliceBuilder` (`tools.bytecode`)

Rewritten against typed `Artifact` records. Key changes:
- Node lookup: `Map<String, DdgNode>` built once from `artifact.ddg().nodes()`, keyed on compound ID
- Caller index: built from `artifact.calltree().edges()`
- `incomingEdges`: follows edges where `edgeInfo` is `LocalEdge` or `HeapEdge` (pattern match on sealed type)
- `param`/`return` crossing logic: unchanged in algorithm, updated to typed access

### Qilin entry point

`metadata.root` from the calltree artifact is used as the Qilin entry point:

```java
PTA pta = PTAFactory.createPTA("insens", view, rootMethod);
pta.run();
```

`insens` = Andersen's flow-insensitive, context-insensitive algorithm. Sufficient for may-alias queries; faster than context-sensitive variants.

## Traversal Algorithm Change in `bwd-slice`

No new crossing arms. The existing intra-method backward walk is extended:

```
was:  follow edges where kind == LOCAL
now:  follow edges where kind == LOCAL || kind == HEAP
```

For a `HeapEdge`, the `from` node is the field write statement. The local being tracked becomes the RHS of the write (the value being stored into the field). Extraction: `stmt` matches `obj.<C: T f> = val` — extract `val`.

## Testing

### Unit: `FieldDepEnricherTest`

- **Single-method heap edge**: two locals that may-alias, one writes a field, one reads — verify `heap` edge emitted
- **No alias, no edge**: non-aliasing locals — verify no `heap` edge
- **Bounded scope excludes out-of-scope writes**: field write in method not in scope set — verify no edge in bounded mode, edge present in unbounded mode
- **Empty scope**: enricher returns artifact unchanged

### Unit: `BwdSliceBuilderTest` (updated)

- Existing 5 tests rewritten against typed `Artifact` records
- New: slice follows a `heap` edge backward to the field write statement

### Integration: `FieldProvenanceService` fixture + `test_field_provenance.sh`

Fixture:
```java
void update(int delta) {
    int base = this.base;       // heap read
    int result = base + delta;  // two parallel local edges
    this.count = result;        // heap write
}

int read() {
    return this.count;          // heap read — seed here
}
```

Seeding `bwd-slice` at `this.count` read in `read()`. Assertions:
- `heap` edge from `this.count` write to `this.count` read
- Two parallel `local` edges into `result = base + delta`
- Serial `heap` edge: `this.base` read appears upstream of `this.count` write
- `param` edge from `delta` to call site in caller
- All four edge kinds present: `LOCAL`, `HEAP`, `PARAM`, `RETURN`

### Integration: `test_bwd_slice.sh` (updated)

Add assertion: at least one `heap`-kind edge present in the output when fixture has a field dependency.

## File Impact

| Action | File |
|--------|------|
| Create | `java/src/main/java/tools/bytecode/FieldDepEnricher.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/Artifact.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/CalltreeGraph.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/CalltreeNode.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/CalltreeEdge.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/DdgGraph.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/DdgNode.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/DdgEdge.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/EdgeInfo.java` (sealed) |
| Create | `java/src/main/java/tools/bytecode/artifact/LocalEdge.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/HeapEdge.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/ParamEdge.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/ReturnEdge.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/StmtKind.java` |
| Create | `java/src/main/java/tools/bytecode/artifact/EdgeKind.java` |
| Create | `java/src/test/java/tools/bytecode/FieldDepEnricherTest.java` |
| Create | `test-fixtures/src/com/example/app/FieldProvenanceService.java` |
| Create | `test-fixtures/tests/test_field_provenance.sh` |
| Modify | `java/src/main/java/tools/bytecode/DdgInterCfgBuilder.java` |
| Modify | `java/src/main/java/tools/bytecode/cli/DdgInterCfgCommand.java` |
| Modify | `java/src/main/java/tools/bytecode/BwdSliceBuilder.java` |
| Modify | `java/src/test/java/tools/bytecode/BwdSliceBuilderTest.java` |
| Modify | `java/src/test/java/tools/bytecode/DdgInterCfgBuilderTest.java` |
| Modify | `test-fixtures/tests/test_bwd_slice.sh` |
| Modify | Python `fw-calltree` command — emit `metadata.root` |
| Modify | `README.md` — updated artifact schema docs |
