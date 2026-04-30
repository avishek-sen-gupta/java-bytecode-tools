# SCIP-Powered Interprocedural CFG Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build source-level interprocedural CFGs by combining Spoon intra-procedural CFGs with SCIP cross-reference data, with configurable recursive depth and namespace stop conditions.

**Architecture:** scip-java runs as a pre-step to produce `index.scip` from the test-fixtures source tree. At analysis time, `ScipIndex` resolves call sites to callee definitions; `SpoonMethodCfgCache` builds and caches per-method CFGs on demand; `IcfgBuilder` stitches them together recursively into an `InterproceduralCfg` data structure. Output layers (DOT/SVG and JSON) are built on top of the data structure.

**Tech Stack:** Java 21, Spoon + spoon-control-flow, `com.sourcegraph:scip` (protobuf), scip-java CLI (pre-step), Graphviz (rendering), existing Maven module `java/`.

---

## Package

`tools.source.icfg` inside `java/src/main/java/`.

---

## Components

### `ScipIndex`

Parses a binary `index.scip` file once at construction. Exposes two queries:

```java
// Returns the SCIP symbol string for the token at the given source position.
// file is relative to the source root (e.g. "com/example/app/OrderService.java").
String symbolAt(String file, int line, int col);

// Returns the source location of a symbol's definition.
SourceLocation locationOf(String symbol);
```

`SourceLocation` is a value type: `(String file, int startLine, int endLine)`.

Internally: two maps — `occurrenceIndex: Map<FilePos, String>` and `definitionIndex: Map<String, SourceLocation>`. Built by iterating `Index.documents` from the SCIP protobuf.

### `SpoonMethodCfgCache`

Wraps a Spoon `Launcher` configured with the source root. Builds `ControlFlowGraph` on demand and caches by `(file, startLine)`:

```java
ControlFlowGraph cfgFor(String file, int startLine);
```

Internally: finds the `CtMethod` whose body starts at or contains `startLine`, runs `ControlFlowBuilder`, calls `simplifyConvergenceNodes()`, stores in cache.

### `IcfgNode`

Wraps a Spoon `ControlFlowNode` and adds:
- `methodSymbol: String` — SCIP symbol of the owning method
- `depth: int` — expansion depth (entry method = 0)

### `IcfgEdge`

```java
enum IcfgEdgeKind { INTRA, CALL, RETURN }
```

- `INTRA` — normal edge within a method's CFG
- `CALL` — from a call-site node to the callee's BEGIN node
- `RETURN` — from a callee's EXIT node back to the post-callsite successor in the caller

### `InterproceduralCfg`

Top-level data structure:

```java
Set<IcfgNode>  vertexSet();
Set<IcfgEdge>  edgeSet();
IcfgNode       entryNode();
Set<IcfgNode>  exitNodes();
```

Same shape as Spoon's `ControlFlowGraph` so existing traversal code composes naturally.

### `IcfgConfig`

```java
int                maxDepth;
Predicate<String>  stopCondition;  // receives declaring type FQN; return true = do not expand
```

Factory helpers (static methods on `StopCondition`):

```java
StopCondition.exact("com.example.app.OrderRepository")
StopCondition.prefix("java.")
StopCondition.any(StopCondition a, StopCondition b, ...)   // OR-combine
```

### `IcfgBuilder`

```java
InterproceduralCfg build(
    String className,
    String methodName,
    ScipIndex index,
    SpoonMethodCfgCache cache,
    IcfgConfig config
);
```

**Algorithm:**

1. Look up `className#methodName` in `ScipIndex` → `SourceLocation`
2. `cache.cfgFor(file, startLine)` → entry method's `ControlFlowGraph`
3. Wrap all nodes as `IcfgNode(depth=0)`, copy INTRA edges
4. For each `IcfgNode` where the statement contains a `CtInvocation`:
   a. Get invocation source position (file, line, col)
   b. `index.symbolAt(file, line, col)` → callee symbol
   c. `index.locationOf(callee symbol)` → `SourceLocation`
   d. Check stop condition on declaring type FQN and depth < maxDepth
   e. If not stopped: recurse with `depth+1`, get callee `InterproceduralCfg`
   f. Add CALL edge: callsite node → callee entryNode
   g. Add RETURN edges: each callee exitNode → successor(s) of callsite node in caller
   h. Remove the direct INTRA edges that bypassed the callsite expansion
5. Return assembled `InterproceduralCfg`

For interface calls, SCIP resolves to the interface method definition. The interface's CFG (typically a single abstract node) is inlined. Expanding into concrete implementations is out of scope.

---

## Output

### `IcfgDotExporter`

```java
String toDot(InterproceduralCfg icfg);
```

- Each method gets a `subgraph cluster_<symbol>` labelled with the simple method name and depth
- Nodes labelled: `[L<line>] <statement>  (depth <d>)`
- INTRA edges: solid black
- CALL edges: dashed blue, labelled "call"
- RETURN edges: dashed gray, labelled "return"

### CLI command `icfg`

New command added to the existing CLI alongside `xtrace`:

```
bytecode.sh <classpath> icfg \
  --from    com.example.app.OrderService \
  --method  processOrder \
  --depth   3 \
  --stop    java. \
  --stop    javax. \
  --index   test-fixtures/index.scip \
  --source  test-fixtures/src \
  --dot     target/icfg.dot \
  --svg     target/icfg.svg
```

Flags:
- `--from` — entry class (required)
- `--method` — entry method name (required)
- `--depth` — max expansion depth (default 3)
- `--stop` — repeatable namespace prefix, becomes `StopCondition.prefix(...)`; OR-combined
- `--stop-exact` — repeatable exact FQN, becomes `StopCondition.exact(...)`; OR-combined with `--stop`
- `--index` — path to `index.scip` (required)
- `--source` — path to source root (required)
- `--dot` — write DOT to this path (optional)
- `--svg` — write SVG to this path (optional)

The command always builds `InterproceduralCfg` in memory first, then writes outputs.

### JSON export

`IcfgJsonExporter` emits the same node/edge JSON shape as the existing call graph format so jspmap can consume it without changes:

```json
{
  "nodes": [{ "id": "...", "label": "...", "method": "...", "depth": 0 }],
  "edges": [{ "from": "...", "to": "...", "kind": "INTRA" }]
}
```

---

## scip-java Pre-Step

Install scip-java (binary release from GitHub or `brew`). Run once against test-fixtures:

```bash
scip-java index \
  --build-tool=javac \
  --output=test-fixtures/index.scip \
  -- javac -g \
       -sourcepath test-fixtures/src \
       -d test-fixtures/classes \
       test-fixtures/src/com/example/app/*.java
```

`test-fixtures/index.scip` is committed to the repo (small binary, changes only when fixtures change). The `build.sh` script gains a step to regenerate it when sources change.

---

## Maven dependency

Add to `java/pom.xml`:

```xml
<dependency>
    <groupId>com.sourcegraph</groupId>
    <artifactId>scip</artifactId>
    <version>0.3.3</version>
</dependency>
```

(Provides the protobuf-generated SCIP classes. Scope: `compile`, since `ScipIndex` is in main sources.)

---

## Testing

All tests use the existing test-fixtures source tree and the `index.scip` generated from it.

- `ScipIndexTest` — unit: symbol lookup at known positions, location resolution for known symbols
- `SpoonMethodCfgCacheTest` — unit: correct CFG returned for a given file+line, cache hit on second call
- `IcfgBuilderTest` — integration: build ICFG for `OrderService.processOrder`, verify:
  - nodes from `processOrder`, `transform`, and `OrderRepository.findById` (depth ≤ 2) present
  - CALL edge from `findById` callsite to callee BEGIN
  - RETURN edge from callee EXIT back to post-callsite node
  - stop condition on `java.` prevents expansion into `String.toUpperCase`
- `IcfgDotExporterTest` — unit: DOT string contains expected subgraph and edge labels
- `IcfgCommandTest` — CLI smoke: `--depth 1` produces valid DOT file
