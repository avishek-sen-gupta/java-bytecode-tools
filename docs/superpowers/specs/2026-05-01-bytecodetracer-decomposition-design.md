# BytecodeTracer Decomposition Design

**Date:** 2026-05-01  
**Status:** Draft

## Context

`BytecodeTracer` (551 lines) is a god class with 8 distinct responsibilities: SootUp view
initialisation, project class enumeration, domain records, Jimple utilities, method resolution,
frame construction, intraprocedural CFG slicing, and line map reporting. It also carries mutable
post-construction state (`callGraphCache`, `projectPrefix`) which violates the immutability
principle in CLAUDE.md.

Goals: **readability** (each class fits in one mental context) and **testability** (each class can
be exercised independently with real compiled bytecode from test fixtures). No new external API
changes visible to `CallGraphBuilder` or `ForwardTracer`.

---

## New Class Map

All classes remain in `tools.bytecode`. No new subpackage.

```
tools.bytecode
├── BytecodeTracer          ← thin facade (public API unchanged for CallGraphBuilder, ForwardTracer)
├── MethodResolver          ← resolves SootMethods by name or line number
├── StmtAnalyzer            ← pure static Jimple utilities
├── FrameBuilder            ← builds CallFrame objects
├── IntraproceduralSlicer   ← backtrack algorithm + trace()
├── LineMapReporter         ← dumpLineMap()
├── CallFrame               ← promoted from BytecodeTracer inner record → top-level
├── FilterConfig            ← promoted from BytecodeTracer inner record → top-level
├── CallGraphBuilder        ← unchanged
└── ForwardTracer           ← unchanged
```

---

## Dependency Chain

```
BytecodeTracer (facade)
  ├── MethodResolver(JavaView)
  ├── StmtAnalyzer                            ← no state, no deps
  ├── FrameBuilder(MethodResolver)
  ├── IntraproceduralSlicer(JavaView, MethodResolver)
  └── LineMapReporter(JavaView)
```

`FrameBuilder` and `IntraproceduralSlicer` call `StmtAnalyzer` static methods directly — no
constructor injection needed for a stateless utility class.

---

## Immutability Fix (CLAUDE.md §no mutable state)

The current `setProjectPrefix` and `setCallGraphCache` setters create mutable post-construction
state on `BytecodeTracer`. Replace with constructor injection.

**Before:**
```java
BytecodeTracer tracer = new BytecodeTracer(parent.classpath);
if (parent.prefix != null) tracer.setProjectPrefix(parent.prefix);
tracer.setCallGraphCache(callGraphFile);   // XtraceCommand
```

**After:**
```java
// BytecodeTracer constructor
public BytecodeTracer(String classpath, String prefix, Path callGraphCache)

// BaseCommand.createTracer() — prefix="" when CLI flag absent (picocli defaultValue = "")
return new BytecodeTracer(parent.classpath, parent.prefix, null);

// XtraceCommand.run()
var tracer = new BytecodeTracer(parent.classpath, parent.prefix, callGraphFile);
```

`prefix` is declared with picocli `defaultValue = ""` so it is never null — no null check in
`createTracer`. `callGraphCache` remains `Path` (nullable) — it is a CLI parameter that may
legitimately be absent and there is no sensible null-object for `Path`. The null check in
`ForwardTracer` (`tracer.getCallGraphCache() != null`) lives in the imperative shell and is
acceptable there. The key win is eliminating the mutable setter, not eliminating null from the
type.

Setters `setProjectPrefix` and `setCallGraphCache` are removed.

---

## Class Specifications

### `StmtAnalyzer`

Stateless static utility class. All methods were previously scattered across `BytecodeTracer`
(some private, some package-private). Consolidating here eliminates duplication between
`buildStmtDetails` (used in `buildFrame`) and the inline re-implementation inside `trace()`.

Map keys (`"line"`, `"jimple"`, `"callTarget"`, `"callArgCount"`, `"calls"`, `"branch"`) are
declared as `static final String` constants on this class — no magic strings in any caller.

`findCallSiteLine` currently has nested for+if loops; rewrite as stream with `flatMap` +
`filter` + `findFirst`.

```java
final class StmtAnalyzer {
  private StmtAnalyzer() {}

  static final String KEY_LINE        = "line";
  static final String KEY_JIMPLE      = "jimple";
  static final String KEY_CALL_TARGET = "callTarget";
  static final String KEY_CALL_ARGS   = "callArgCount";
  static final String KEY_CALLS       = "calls";
  static final String KEY_BRANCH      = "branch";

  static int stmtLine(Stmt stmt)
  static Optional<AbstractInvokeExpr> extractInvoke(Stmt stmt)
  static int findCallSiteLine(CallFrame caller, CallFrame callee)   // stream-based, no nested loops
  static List<Map<String, Object>> buildStmtDetails(List<Stmt> stmts)
  static List<Map<String, Object>> deduplicateToSourceLines(List<Map<String, Object>> details)
  static List<Stmt> stmtsAtLine(StmtGraph<?> graph, int line)
}
```

### `MethodResolver`

All method-lookup logic. Package-visible constructor; callable from tests with a real `JavaView`.

`resolveCallee` currently returns `null` when not found — violates no-null principle. Replaced
with `Optional<SootMethod>`. All callers updated accordingly (internal to `MethodResolver` and
`IntraproceduralSlicer`).

`findMethodsContainingLine` currently uses a for+if loop with mutation; rewrite as stream with
`filter` + `collect`.

```java
class MethodResolver {
  MethodResolver(JavaView view)

  SootMethod resolveByName(String className, String methodName)   // throws if absent/ambiguous
  SootMethod resolveByLine(String className, int line)            // throws if absent
  // package-private:
  Optional<SootMethod> resolveCallee(MethodSignature sig)
  List<SootMethod> findMethodsContainingLine(JavaSootClass clazz, int line)  // stream-based
}
```

### `FrameBuilder`

Builds full and lightweight `CallFrame` objects. Calls `StmtAnalyzer` directly for statement
analysis. Uses `StmtAnalyzer` constants for all map keys.

```java
class FrameBuilder {
  FrameBuilder(MethodResolver resolver)

  CallFrame buildFrame(SootMethod method, String sig)
  CallFrame buildFlatFrame(SootMethod method, String sig)
}
```

### `IntraproceduralSlicer`

Encapsulates the backward-reachability CFG algorithm. Calls `StmtAnalyzer.buildStmtDetails` and
`StmtAnalyzer.deduplicateToSourceLines` — eliminating the duplication that existed in `trace()`.

`backtrack` currently uses mutation-heavy BFS loops; implementation may keep imperative
BFS/queue style since graph traversal with a mutable `Queue` and `visited` set is inherently
stateful — no functional equivalent is idiomatic in Java. However, `stmts` collection and
intermediate result building must use streams where applicable.

```java
class IntraproceduralSlicer {
  IntraproceduralSlicer(JavaView view, MethodResolver resolver)

  Map<String, Object> trace(String className, int fromLine, int toLine)
  // private: backtrack(StmtGraph<?>, Set<Stmt> from, Set<Stmt> to)
}
```

### `LineMapReporter`

`dumpLineMap` currently iterates methods with a for loop and mutation; rewrite using stream +
`Collectors.toList` throughout.

```java
class LineMapReporter {
  LineMapReporter(JavaView view)

  Map<String, Object> dumpLineMap(String className)
}
```

### `CallFrame` and `FilterConfig` (promoted records)

Both become top-level files in `tools.bytecode`. `FilterConfig.shouldRecurse` currently uses
two nested for+if loops — rewrite using `anyMatch` / `noneMatch` on the prefix lists.
`FilterConfig.load` stays as-is (imperative shell: file I/O).

### `BytecodeTracer` (facade)

Constructor wires collaborators. All public methods delegate:

```java
public class BytecodeTracer {
  private final JavaView view;
  private final String projectPrefix;
  private final Path callGraphCache;
  private final MethodResolver methodResolver;
  private final FrameBuilder frameBuilder;
  private final IntraproceduralSlicer slicer;
  private final LineMapReporter lineMapReporter;

  public BytecodeTracer(String classpath, String prefix, Path callGraphCache) {
    this.view = buildView(classpath);
    this.projectPrefix = prefix;
    this.callGraphCache = callGraphCache;
    this.methodResolver = new MethodResolver(view);
    this.frameBuilder = new FrameBuilder(methodResolver);
    this.slicer = new IntraproceduralSlicer(view, methodResolver);
    this.lineMapReporter = new LineMapReporter(view);
  }

  // Delegating public API (unchanged signatures):
  public List<JavaSootClass> getProjectClasses()
  public Path getCallGraphCache()
  public Map<String, Object> trace(String className, int fromLine, int toLine)
  public Map<String, Object> dumpLineMap(String className)

  // Package-visible delegation for CallGraphBuilder / ForwardTracer:
  SootMethod resolveMethodByName(String className, String methodName)
  SootMethod resolveMethod(String className, int line)
  CallFrame buildFrame(SootMethod method, String sig)
  CallFrame buildFlatFrame(SootMethod method, String sig)
}
```

`System.err.println` calls in the constructor and `getProjectClasses` are replaced with `log`
calls (SLF4J). `System.err.println` is permitted only in CLI `main()` entry points per
CLAUDE.md; it is not appropriate in domain classes.

---

## CLAUDE.md Compliance Requirements

These violations exist in the current code and must be fixed as part of extraction — not deferred.

| Violation | Location | Fix |
|-----------|----------|-----|
| `for` loop + `result.add()` mutation | `buildStmtDetails`, `findMethodsContainingLine`, `stmtsAtLine`, `dumpLineMap` | Rewrite with `stream().map().collect()` |
| Nested `for`+`if` loops | `FilterConfig.shouldRecurse`, `findCallSiteLine` | Rewrite with `anyMatch`/`noneMatch`/`flatMap`+`filter` |
| Returns `null` | `resolveCallee` | Return `Optional<SootMethod>` |
| Magic string map keys | `buildStmtDetails`, `deduplicateToSourceLines`, `buildFlatFrame`, `trace` | Constants on `StmtAnalyzer` |
| `System.err.println` in domain classes | `BytecodeTracer` constructor, `getProjectClasses` | `log.info` / `log.debug` |

**Known deferred violation:** `Map<String, Object>` as the return type of `trace()` and
`dumpLineMap()` is a weak public type. Replacing it with typed records is out of scope for this
decomposition — it would require changes throughout the Python pipeline. Noted for a future pass.

---

## Duplication Eliminated

`buildStmtDetails` logic currently exists twice:
1. `BytecodeTracer.buildStmtDetails` (lines 314–336) — called by `buildFrame`
2. Inline inside `BytecodeTracer.trace` (lines 456–481)

After extraction, both `FrameBuilder` and `IntraproceduralSlicer` call
`StmtAnalyzer.buildStmtDetails`. The duplication is gone.

---

## Files Changed

| File | Change |
|------|--------|
| `BytecodeTracer.java` | Gutted to thin facade; constructor updated |
| `MethodResolver.java` | New |
| `StmtAnalyzer.java` | New |
| `FrameBuilder.java` | New |
| `IntraproceduralSlicer.java` | New |
| `LineMapReporter.java` | New |
| `CallFrame.java` | New (promoted from inner record) |
| `FilterConfig.java` | New (promoted from inner record) |
| `cli/BaseCommand.java` | `createTracer()` uses 3-arg constructor |
| `cli/XtraceCommand.java` | Inline `new BytecodeTracer(...)` with callGraphFile |

`CallGraphBuilder` and `ForwardTracer` are **unchanged** — they continue to receive
`BytecodeTracer` and call the same package-visible methods.

---

## Testing

- Each new class gets its own focused test class (e.g., `MethodResolverTest`,
  `IntraproceduralSlicerTest`) exercising it directly with real bytecode from
  `test-fixtures/`.
- Existing `BytecodeTracerResolveByNameTest` tests are migrated to `MethodResolverTest`.
- `BytecodeTracer` integration tests (if any) remain as-is — they cover the facade end-to-end.
- TDD order: write failing test for each class before implementing it.

---

## Order of Implementation

1. `CallFrame`, `FilterConfig` — top-level records (pure move, no logic change)
2. `StmtAnalyzer` — static utils (pure move + consolidation)
3. `MethodResolver` — depends only on `JavaView`
4. `FrameBuilder` — depends on `MethodResolver` + `StmtAnalyzer`
5. `IntraproceduralSlicer` — depends on `JavaView` + `MethodResolver` + `StmtAnalyzer`
6. `LineMapReporter` — depends only on `JavaView`
7. `BytecodeTracer` facade — wires everything; update constructor; remove setters
8. CLI updates — `BaseCommand`, `XtraceCommand`
