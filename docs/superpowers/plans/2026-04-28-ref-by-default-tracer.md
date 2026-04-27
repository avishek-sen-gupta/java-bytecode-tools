# Ref-by-Default Call Tree Tracer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `ForwardTracer`'s single-pass recursive tracer with a two-pass architecture where every method (except root) is a ref by default. Expansion becomes a deliberate user choice via `ftrace_expand_refs.py`.

**Architecture:** Pass 1 (Discover) walks the prebuilt call graph via DFS, classifying each method as NORMAL/CYCLE/FILTERED. Pass 2 (Build) iterates discovered methods in a flat loop, constructing CFGs in isolation — no recursion, no `globalVisited`. The output wraps the root trace and a flat refIndex in an envelope `{"trace": ..., "refIndex": {...}}`.

**Tech Stack:** Java 21 (SootUp), Python 3.13 (uv), JUnit 5, pytest, bash E2E tests

**Spec:** `docs/superpowers/specs/2026-04-28-ref-by-default-tracer-design.md`

---

## File Map

### Java — New Files

| File | Responsibility |
|---|---|
| `java/src/main/java/tools/bytecode/Classification.java` | Enum: `NORMAL`, `CYCLE`, `FILTERED` |
| `java/src/main/java/tools/bytecode/DiscoveryResult.java` | Record: `normalMethods` set + `calleeMap` with per-call-site classification |
| `java/src/test/java/tools/bytecode/DiscoverReachableTest.java` | Unit tests for Pass 1 discovery |
| `java/src/test/java/tools/bytecode/BuildRefChildTest.java` | Unit tests for child node builder |

### Java — Modified Files

| File | What Changes |
|---|---|
| `java/src/main/java/tools/bytecode/ForwardTracer.java` | Delete `buildForwardNode`. Add `discoverReachable`, `discoverDFS`, `classifyCallee`, `buildChildNode`, `buildMethodCFG`, `resolveCallSiteLine`, `extractClassName`, `extractMethodName`. Rewrite `traceForward`. Add field name constants. |

### Python — Modified Files

| File | What Changes |
|---|---|
| `python/ftrace_expand_refs.py` | `main()`: support both `slice` and `trace` envelope keys |
| `python/ftrace_semantic.py` | `main()`: detect envelope, extract `trace` key before calling `transform` |

### E2E Tests — Modified Files

| File | What Changes |
|---|---|
| `test-fixtures/tests/test_xtrace_forward.sh` | Add `.trace.` prefix to all root-level jq queries; add refIndex assertion |
| `test-fixtures/tests/test_xtrace_exception.sh` | Add `.trace.` prefix to root-level jq queries |
| `test-fixtures/tests/test_xtrace_nested_exception.sh` | Add `.trace.` prefix to root-level jq queries |
| `test-fixtures/tests/test_xtrace_edges_pipeline.sh` | Add `.trace.` prefix; change child edge check to query refIndex |
| `test-fixtures/tests/test_ftrace_slice.sh` | Add `ftrace-expand-refs` step before `ftrace-slice` in all pipelines |

### E2E Tests — Unchanged Files

| File | Why Unchanged |
|---|---|
| `test-fixtures/tests/test_xtrace_forward_filter.sh` | Uses `.. | objects | select(.filtered?)` recursive descent — works on envelope |
| `test-fixtures/lib-test.sh` | Test infrastructure — no changes needed |

### Java — Unchanged Files

| File | Why Unchanged |
|---|---|
| `java/src/main/java/tools/bytecode/BytecodeTracer.java` | Shared infrastructure — `CallFrame`, `FilterConfig`, `findCallSiteLine`, `buildFrame` all remain as-is |
| `java/src/main/java/tools/bytecode/BackwardTracer.java` | Uses `buildBlockTrace()` which stays package-visible and unchanged |
| `java/src/main/java/tools/bytecode/cli/XtraceCommand.java` | `writeOutput(Map<String, Object>)` handles any map shape |
| `java/src/main/java/tools/bytecode/cli/BaseCommand.java` | Generic JSON serialization — works for envelope |

---

## Task 1: Domain Types

Create the new domain types that Pass 1 and Pass 2 depend on. Add field name constants and signature parsing helpers to `ForwardTracer`.

**Files:**
- Create: `java/src/main/java/tools/bytecode/Classification.java`
- Create: `java/src/main/java/tools/bytecode/DiscoveryResult.java`
- Modify: `java/src/main/java/tools/bytecode/ForwardTracer.java`

### Step 1.1: Create Classification enum

- [ ] **Write `Classification.java`**

```java
package tools.bytecode;

/** Classification of a method encountered during call graph discovery. */
public enum Classification {
  NORMAL,
  CYCLE,
  FILTERED
}
```

### Step 1.2: Create DiscoveryResult record

- [ ] **Write `DiscoveryResult.java`**

```java
package tools.bytecode;

import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Result of Pass 1 call graph discovery.
 *
 * @param normalMethods signatures of methods that should have full CFGs built
 * @param calleeMap     for each discovered method, the list of callees with per-call-site classification
 */
public record DiscoveryResult(
    Set<String> normalMethods,
    Map<String, List<CalleeEntry>> calleeMap) {

  /** A single callee at a specific call site, with its classification. */
  public record CalleeEntry(String signature, Classification classification) {}

  public DiscoveryResult {
    normalMethods = Set.copyOf(normalMethods);
    calleeMap = Map.copyOf(calleeMap);
  }
}
```

### Step 1.3: Add field name constants and signature helpers to ForwardTracer

- [ ] **Add constants and helpers at the top of `ForwardTracer.java`**

Add these right after the class declaration (line 21), before the `tracer` field:

```java
  // JSON field name constants
  static final String F_CLASS = "class";
  static final String F_METHOD = "method";
  static final String F_METHOD_SIGNATURE = "methodSignature";
  static final String F_CALL_SITE_LINE = "callSiteLine";
  static final String F_REF = "ref";
  static final String F_CYCLE = "cycle";
  static final String F_FILTERED = "filtered";
  static final String F_LINE_START = "lineStart";
  static final String F_LINE_END = "lineEnd";
  static final String F_SOURCE_LINE_COUNT = "sourceLineCount";
  static final String F_SOURCE_TRACE = "sourceTrace";
  static final String F_BLOCKS = "blocks";
  static final String F_EDGES = "edges";
  static final String F_TRAPS = "traps";
  static final String F_CHILDREN = "children";
  static final String F_FROM_CLASS = "fromClass";
  static final String F_FROM_LINE = "fromLine";
  static final String F_TRACE = "trace";
  static final String F_REF_INDEX = "refIndex";

  /** Extract the fully qualified class name from a SootUp signature like {@code <com.example.Foo: void bar(int)>}. */
  static String extractClassName(String sig) {
    return sig.substring(1, sig.indexOf(':'));
  }

  /** Extract the method name from a SootUp signature like {@code <com.example.Foo: void bar(int)>}. */
  static String extractMethodName(String sig) {
    return sig.substring(sig.lastIndexOf(' ') + 1, sig.indexOf('('));
  }
```

### Step 1.4: Verify it compiles

- [ ] **Run Maven compile**

Run: `cd java && mvn compile -q`
Expected: BUILD SUCCESS (no errors)

### Step 1.5: Commit

- [ ] **Commit domain types**

```bash
git add java/src/main/java/tools/bytecode/Classification.java \
        java/src/main/java/tools/bytecode/DiscoveryResult.java \
        java/src/main/java/tools/bytecode/ForwardTracer.java
git commit -m "feat: add Classification enum, DiscoveryResult record, and field constants for ref-by-default tracer"
```

---

## Task 2: Pass 1 — Discovery (TDD)

Implement `discoverReachable`, the static method that walks the call graph and classifies methods. Fully testable without SootUp — accepts `Set<String> knownSignatures` instead of `Map<String, SootMethod>`.

**Files:**
- Create: `java/src/test/java/tools/bytecode/DiscoverReachableTest.java`
- Modify: `java/src/main/java/tools/bytecode/ForwardTracer.java`

### Step 2.1: Write failing tests

- [ ] **Write `DiscoverReachableTest.java`**

```java
package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class DiscoverReachableTest {

  private static final BytecodeTracer.FilterConfig NO_FILTER =
      new BytecodeTracer.FilterConfig(null, null);

  @Nested
  class SimpleChainTest {

    @Test
    void discoversAllMethodsInChain() {
      // A → B → C
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of("B"));
      callGraph.put("B", List.of("C"));
      callGraph.put("C", List.of());
      Set<String> known = Set.of("A", "B", "C");

      DiscoveryResult result = ForwardTracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A", "B", "C"), result.normalMethods());
      // A has callee B (NORMAL)
      assertEquals(1, result.calleeMap().get("A").size());
      assertEquals("B", result.calleeMap().get("A").get(0).signature());
      assertEquals(Classification.NORMAL, result.calleeMap().get("A").get(0).classification());
      // B has callee C (NORMAL)
      assertEquals("C", result.calleeMap().get("B").get(0).signature());
      assertEquals(Classification.NORMAL, result.calleeMap().get("B").get(0).classification());
      // C has no callees
      assertTrue(result.calleeMap().get("C").isEmpty());
    }
  }

  @Nested
  class CycleTest {

    @Test
    void detectsCycleInPathAncestors() {
      // A → B → A (cycle)
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of("B"));
      callGraph.put("B", List.of("A"));
      Set<String> known = Set.of("A", "B");

      DiscoveryResult result = ForwardTracer.discoverReachable("A", callGraph, known, NO_FILTER);

      // Both are NORMAL (cycle is per-call-site, not per-method)
      assertEquals(Set.of("A", "B"), result.normalMethods());
      // B's callee A is classified CYCLE
      assertEquals(1, result.calleeMap().get("B").size());
      assertEquals("A", result.calleeMap().get("B").get(0).signature());
      assertEquals(Classification.CYCLE, result.calleeMap().get("B").get(0).classification());
    }

    @Test
    void selfRecursion() {
      // A → A
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of("A"));
      Set<String> known = Set.of("A");

      DiscoveryResult result = ForwardTracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A"), result.normalMethods());
      assertEquals(1, result.calleeMap().get("A").size());
      assertEquals(Classification.CYCLE, result.calleeMap().get("A").get(0).classification());
    }
  }

  @Nested
  class FilteredTest {

    @Test
    void unknownSignatureIsFiltered() {
      // A → B, but B not in knownSignatures
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of("B"));
      Set<String> known = Set.of("A");

      DiscoveryResult result = ForwardTracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A"), result.normalMethods());
      assertEquals(1, result.calleeMap().get("A").size());
      assertEquals(Classification.FILTERED, result.calleeMap().get("A").get(0).classification());
    }

    @Test
    void filterConfigRejectsClass() {
      // A → <com.ext.Lib: void foo()>, filter stops com.ext
      String calleeSig = "<com.ext.Lib: void foo()>";
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of(calleeSig));
      Set<String> known = Set.of("A", calleeSig);
      BytecodeTracer.FilterConfig filter =
          new BytecodeTracer.FilterConfig(null, List.of("com.ext"));

      DiscoveryResult result = ForwardTracer.discoverReachable("A", callGraph, known, filter);

      assertEquals(Set.of("A"), result.normalMethods());
      assertEquals(Classification.FILTERED, result.calleeMap().get("A").get(0).classification());
    }
  }

  @Nested
  class DiamondTest {

    @Test
    void diamondVisitsSharedNodeOnce() {
      // A → B, A → C, B → D, C → D
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of("B", "C"));
      callGraph.put("B", List.of("D"));
      callGraph.put("C", List.of("D"));
      callGraph.put("D", List.of());
      Set<String> known = Set.of("A", "B", "C", "D");

      DiscoveryResult result = ForwardTracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A", "B", "C", "D"), result.normalMethods());
      // A has two callees, both NORMAL
      assertEquals(2, result.calleeMap().get("A").size());
      // D appears as NORMAL callee of both B and C
      assertEquals(Classification.NORMAL, result.calleeMap().get("B").get(0).classification());
      assertEquals(Classification.NORMAL, result.calleeMap().get("C").get(0).classification());
    }
  }

  @Nested
  class EmptyCalleesTest {

    @Test
    void leafMethodHasEmptyCalleeList() {
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of());
      Set<String> known = Set.of("A");

      DiscoveryResult result = ForwardTracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A"), result.normalMethods());
      assertTrue(result.calleeMap().get("A").isEmpty());
    }

    @Test
    void methodNotInCallGraphHasEmptyCalleeList() {
      // A is in known but not in call graph
      Map<String, List<String>> callGraph = Map.of();
      Set<String> known = Set.of("A");

      DiscoveryResult result = ForwardTracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A"), result.normalMethods());
      assertTrue(result.calleeMap().get("A").isEmpty());
    }
  }
}
```

### Step 2.2: Run tests — verify they fail

- [ ] **Run tests to see compilation failure**

Run: `cd java && mvn test -pl . -Dtest=DiscoverReachableTest -q 2>&1 | tail -5`
Expected: Compilation error — `discoverReachable` does not exist yet.

### Step 2.3: Implement discovery methods

- [ ] **Add `discoverReachable`, `discoverDFS`, and `classifyCallee` to `ForwardTracer.java`**

Add these after the `extractMethodName` helper, before the existing `traceForward` method:

```java
  /**
   * Pass 1 — Discover all reachable methods from a root signature via DFS over the call graph.
   *
   * <p>Pure function over the call graph — no SootUp access. Testable with synthetic graphs.
   *
   * @param rootSig         entry method signature
   * @param callGraph       prebuilt caller→callees map
   * @param knownSignatures set of signatures that have bodies (project methods)
   * @param filter          class-level allow/stop filter (null-safe)
   * @return discovery result with classifications and callee lists
   */
  static DiscoveryResult discoverReachable(
      String rootSig,
      Map<String, List<String>> callGraph,
      Set<String> knownSignatures,
      BytecodeTracer.FilterConfig filter) {
    Set<String> normalMethods = new LinkedHashSet<>();
    Map<String, List<DiscoveryResult.CalleeEntry>> calleeMap = new LinkedHashMap<>();
    Set<String> pathAncestors = new LinkedHashSet<>();
    Set<String> visited = new HashSet<>();

    discoverDFS(rootSig, callGraph, knownSignatures, filter,
        pathAncestors, visited, normalMethods, calleeMap);

    return new DiscoveryResult(normalMethods, calleeMap);
  }

  private static void discoverDFS(
      String sig,
      Map<String, List<String>> callGraph,
      Set<String> knownSignatures,
      BytecodeTracer.FilterConfig filter,
      Set<String> pathAncestors,
      Set<String> visited,
      Set<String> normalMethods,
      Map<String, List<DiscoveryResult.CalleeEntry>> calleeMap) {
    if (visited.contains(sig)) return;
    visited.add(sig);

    // Root passes knownSignatures check at the call site, but a callee
    // may reach here via NORMAL classification before its own body is checked.
    // Filter also applies to the method itself (not just as a callee).
    String className = extractClassName(sig);
    if (!knownSignatures.contains(sig)
        || (filter != null && !filter.shouldRecurse(className))) {
      return;
    }

    normalMethods.add(sig);
    pathAncestors.add(sig);

    List<String> callees = callGraph.getOrDefault(sig, List.of());
    List<DiscoveryResult.CalleeEntry> entries = new ArrayList<>();
    for (String calleeSig : callees) {
      Classification classification =
          classifyCallee(calleeSig, pathAncestors, knownSignatures, filter);
      entries.add(new DiscoveryResult.CalleeEntry(calleeSig, classification));
      if (classification == Classification.NORMAL) {
        discoverDFS(calleeSig, callGraph, knownSignatures, filter,
            pathAncestors, visited, normalMethods, calleeMap);
      }
    }

    pathAncestors.remove(sig);
    calleeMap.put(sig, List.copyOf(entries));
  }

  private static Classification classifyCallee(
      String calleeSig,
      Set<String> pathAncestors,
      Set<String> knownSignatures,
      BytecodeTracer.FilterConfig filter) {
    if (pathAncestors.contains(calleeSig)) return Classification.CYCLE;
    String calleeClass = extractClassName(calleeSig);
    if (!knownSignatures.contains(calleeSig)
        || (filter != null && !filter.shouldRecurse(calleeClass))) {
      return Classification.FILTERED;
    }
    return Classification.NORMAL;
  }
```

### Step 2.4: Run tests — verify they pass

- [ ] **Run discovery tests**

Run: `cd java && mvn test -pl . -Dtest=DiscoverReachableTest -q`
Expected: All tests PASS.

### Step 2.5: Commit

- [ ] **Commit Pass 1**

```bash
git add java/src/test/java/tools/bytecode/DiscoverReachableTest.java \
        java/src/main/java/tools/bytecode/ForwardTracer.java
git commit -m "feat: implement Pass 1 call graph discovery with TDD tests"
```

---

## Task 3: Child Node Builder (TDD)

Implement `buildChildNode`, the static method that creates a ref/cycle/filtered node from a callee signature and classification. This is used by Pass 2 to attach children to each method's CFG.

**Files:**
- Create: `java/src/test/java/tools/bytecode/BuildRefChildTest.java`
- Modify: `java/src/main/java/tools/bytecode/ForwardTracer.java`

### Step 3.1: Write failing tests

- [ ] **Write `BuildRefChildTest.java`**

```java
package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class BuildRefChildTest {

  private static final String SIG = "<com.example.Foo: void bar(int)>";

  @Nested
  class NormalRefTest {

    @Test
    void normalClassificationProducesRefNode() {
      Map<String, Object> node =
          ForwardTracer.buildChildNode(SIG, Classification.NORMAL, 42);

      assertEquals("com.example.Foo", node.get(ForwardTracer.F_CLASS));
      assertEquals("bar", node.get(ForwardTracer.F_METHOD));
      assertEquals(SIG, node.get(ForwardTracer.F_METHOD_SIGNATURE));
      assertEquals(true, node.get(ForwardTracer.F_REF));
      assertNull(node.get(ForwardTracer.F_CYCLE));
      assertNull(node.get(ForwardTracer.F_FILTERED));
      assertEquals(42, node.get(ForwardTracer.F_CALL_SITE_LINE));
    }
  }

  @Nested
  class CycleTest {

    @Test
    void cycleClassificationProducesCycleNode() {
      Map<String, Object> node =
          ForwardTracer.buildChildNode(SIG, Classification.CYCLE, 10);

      assertEquals(true, node.get(ForwardTracer.F_CYCLE));
      assertNull(node.get(ForwardTracer.F_REF));
      assertNull(node.get(ForwardTracer.F_FILTERED));
    }
  }

  @Nested
  class FilteredTest {

    @Test
    void filteredClassificationProducesFilteredNode() {
      Map<String, Object> node =
          ForwardTracer.buildChildNode(SIG, Classification.FILTERED, 5);

      assertEquals(true, node.get(ForwardTracer.F_FILTERED));
      assertNull(node.get(ForwardTracer.F_REF));
      assertNull(node.get(ForwardTracer.F_CYCLE));
    }
  }

  @Nested
  class CallSiteLineTest {

    @Test
    void positiveCallSiteLineIncluded() {
      Map<String, Object> node =
          ForwardTracer.buildChildNode(SIG, Classification.NORMAL, 42);

      assertEquals(42, node.get(ForwardTracer.F_CALL_SITE_LINE));
    }

    @Test
    void negativeCallSiteLineOmitted() {
      Map<String, Object> node =
          ForwardTracer.buildChildNode(SIG, Classification.NORMAL, -1);

      assertNull(node.get(ForwardTracer.F_CALL_SITE_LINE));
    }

    @Test
    void zeroCallSiteLineOmitted() {
      Map<String, Object> node =
          ForwardTracer.buildChildNode(SIG, Classification.NORMAL, 0);

      assertNull(node.get(ForwardTracer.F_CALL_SITE_LINE));
    }
  }

  @Nested
  class SignatureParsingTest {

    @Test
    void extractsClassAndMethodFromSignature() {
      Map<String, Object> node =
          ForwardTracer.buildChildNode(
              "<com.example.app.OrderService: void processOrder(int)>",
              Classification.NORMAL,
              7);

      assertEquals("com.example.app.OrderService", node.get(ForwardTracer.F_CLASS));
      assertEquals("processOrder", node.get(ForwardTracer.F_METHOD));
    }
  }
}
```

### Step 3.2: Run tests — verify they fail

- [ ] **Run tests to see compilation failure**

Run: `cd java && mvn test -pl . -Dtest=BuildRefChildTest -q 2>&1 | tail -5`
Expected: Compilation error — `buildChildNode` does not exist yet.

### Step 3.3: Implement buildChildNode

- [ ] **Add `buildChildNode` to `ForwardTracer.java`**

Add after the `classifyCallee` method:

```java
  /**
   * Build a child node for a callee. Always produces a leaf (ref, cycle, or filtered).
   *
   * @param calleeSig      callee method signature
   * @param classification how this callee was classified during discovery
   * @param callSiteLine   source line of the call site (omitted if <= 0)
   * @return map suitable for inclusion in the "children" list
   */
  static Map<String, Object> buildChildNode(
      String calleeSig, Classification classification, int callSiteLine) {
    Map<String, Object> node = new LinkedHashMap<>();
    node.put(F_CLASS, extractClassName(calleeSig));
    node.put(F_METHOD, extractMethodName(calleeSig));
    node.put(F_METHOD_SIGNATURE, calleeSig);

    if (callSiteLine > 0) {
      node.put(F_CALL_SITE_LINE, callSiteLine);
    }

    switch (classification) {
      case NORMAL -> node.put(F_REF, true);
      case CYCLE -> node.put(F_CYCLE, true);
      case FILTERED -> node.put(F_FILTERED, true);
    }

    return node;
  }
```

### Step 3.4: Run tests — verify they pass

- [ ] **Run child builder tests**

Run: `cd java && mvn test -pl . -Dtest=BuildRefChildTest -q`
Expected: All tests PASS.

### Step 3.5: Commit

- [ ] **Commit child builder**

```bash
git add java/src/test/java/tools/bytecode/BuildRefChildTest.java \
        java/src/main/java/tools/bytecode/ForwardTracer.java
git commit -m "feat: implement buildChildNode with TDD tests"
```

---

## Task 4: Pass 2 — Build + Integration

Rewrite `traceForward()` to use the two-pass architecture. Add `buildMethodCFG` (instance method — needs `this.tracer` for `buildFrame` and `buildBlockTrace`). Add `resolveCallSiteLine` helper. Delete `buildForwardNode`. This is the integration task — the unit-tested building blocks from Tasks 2-3 are composed here.

**Files:**
- Modify: `java/src/main/java/tools/bytecode/ForwardTracer.java`

### Step 4.1: Add resolveCallSiteLine helper

- [ ] **Add `resolveCallSiteLine` to `ForwardTracer.java`**

Add after `buildChildNode`:

```java
  /**
   * Resolve the source line where a caller invokes a callee. Builds a lightweight
   * CallFrame for the callee (no body needed) and delegates to
   * {@link BytecodeTracer#findCallSiteLine}.
   */
  private static int resolveCallSiteLine(
      BytecodeTracer.CallFrame callerFrame, String calleeSig) {
    String calleeClass = extractClassName(calleeSig);
    String calleeMethod = extractMethodName(calleeSig);
    BytecodeTracer.CallFrame calleeFrame =
        new BytecodeTracer.CallFrame(
            calleeClass, calleeMethod, calleeSig, -1, -1, List.of(), List.of());
    return BytecodeTracer.findCallSiteLine(callerFrame, calleeFrame);
  }
```

### Step 4.2: Add buildMethodCFG

- [ ] **Add `buildMethodCFG` to `ForwardTracer.java`**

Add after `resolveCallSiteLine`:

```java
  /**
   * Pass 2 — Build a single method's CFG with ref children.
   *
   * <p>No recursion. Each callee becomes a ref/cycle/filtered leaf via
   * {@link #buildChildNode}. Called in a flat loop for all discovered methods.
   */
  private Map<String, Object> buildMethodCFG(
      String sig,
      Map<String, SootMethod> sigToMethod,
      DiscoveryResult discovery) {
    SootMethod method = sigToMethod.get(sig);
    BytecodeTracer.CallFrame frame = tracer.buildFrame(method, sig);

    Map<String, Object> node = new LinkedHashMap<>();
    node.put(F_CLASS, frame.className());
    node.put(F_METHOD, frame.methodName());
    node.put(F_METHOD_SIGNATURE, sig);
    node.put(F_LINE_START, frame.entryLine());
    node.put(F_LINE_END, frame.exitLine());
    node.put(F_SOURCE_LINE_COUNT, frame.exitLine() - frame.entryLine() + 1);
    node.put(F_SOURCE_TRACE, frame.sourceTrace());

    Map<String, Object> blockInfo = buildBlockTrace(method);
    node.put(F_BLOCKS, blockInfo.get("blocks"));
    node.put(F_EDGES, blockInfo.get("edges"));
    node.put(F_TRAPS, blockInfo.get("traps"));

    List<DiscoveryResult.CalleeEntry> callees =
        discovery.calleeMap().getOrDefault(sig, List.of());
    List<Map<String, Object>> children = new ArrayList<>();
    for (DiscoveryResult.CalleeEntry entry : callees) {
      int csLine = resolveCallSiteLine(frame, entry.signature());
      children.add(buildChildNode(entry.signature(), entry.classification(), csLine));
    }
    node.put(F_CHILDREN, children);

    return node;
  }
```

### Step 4.3: Rewrite traceForward

- [ ] **Replace the body of `traceForward` (lines 29-68)**

Replace the entire `traceForward` method body with:

```java
  public Map<String, Object> traceForward(
      String fromClass, int fromLine, BytecodeTracer.FilterConfig filter) throws IOException {
    SootMethod entryMethod = tracer.resolveMethod(fromClass, fromLine);
    String entrySig = entryMethod.getSignature().toString();

    // Index all project methods
    Map<String, SootMethod> sigToMethod = new LinkedHashMap<>();
    for (JavaSootClass cls : tracer.getProjectClasses()) {
      for (SootMethod method : cls.getMethods()) {
        if (!method.hasBody()) continue;
        sigToMethod.put(method.getSignature().toString(), method);
      }
    }
    System.err.println("Methods: " + sigToMethod.size());

    // Load call graph
    Map<String, List<String>> callerToCallees = loadForwardCallGraph();

    // Pass 1 — Discover
    System.err.println("Discovering reachable methods from " + entrySig + "...");
    DiscoveryResult discovery =
        discoverReachable(entrySig, callerToCallees, sigToMethod.keySet(), filter);
    System.err.println("Discovered: " + discovery.normalMethods().size() + " methods");

    // Pass 2 — Build root
    System.err.println("Building CFGs...");
    Map<String, Object> root = buildMethodCFG(entrySig, sigToMethod, discovery);
    root.put(F_FROM_CLASS, fromClass);
    root.put(F_FROM_LINE, fromLine);

    // Pass 2 — Build refIndex (all NORMAL methods except root)
    Map<String, Object> refIndex = new LinkedHashMap<>();
    for (String sig : discovery.normalMethods()) {
      if (sig.equals(entrySig)) continue;
      refIndex.put(sig, buildMethodCFG(sig, sigToMethod, discovery));
    }

    // Envelope
    Map<String, Object> envelope = new LinkedHashMap<>();
    envelope.put(F_TRACE, root);
    envelope.put(F_REF_INDEX, refIndex);

    System.err.println("Done: " + (refIndex.size() + 1) + " method CFGs");
    return envelope;
  }
```

### Step 4.4: Delete buildForwardNode

- [ ] **Delete the entire `buildForwardNode` method (lines 83-178 in the original file)**

Remove the method and the `globalVisited` field (which was a local var in `traceForward`, already gone from the rewrite above). The method is no longer called anywhere.

### Step 4.5: Verify compilation

- [ ] **Run Maven compile**

Run: `cd java && mvn compile -q`
Expected: BUILD SUCCESS. `BackwardTracer` still compiles because `buildBlockTrace` is unchanged.

### Step 4.6: Run existing Java tests

- [ ] **Run all Java tests**

Run: `cd java && mvn test -q`
Expected: All existing tests (CoverageGapFillTest, DiscoverReachableTest, BuildRefChildTest) PASS.

### Step 4.7: Commit

- [ ] **Commit Pass 2 integration**

```bash
git add java/src/main/java/tools/bytecode/ForwardTracer.java
git commit -m "feat: rewrite traceForward to two-pass ref-by-default architecture

Pass 1 discovers reachable methods via call graph DFS.
Pass 2 builds CFGs in a flat loop with ref children.
Outputs envelope: {trace: root, refIndex: {...}}.
Deletes single-pass recursive buildForwardNode."
```

---

## Task 5: Python Compatibility

Update `ftrace_expand_refs.py` and `ftrace_semantic.py` to handle the new envelope format. Both tools must continue working with the old bare-tree format for backward compatibility (e.g., expanded trees from `ftrace-expand-refs` output).

**Files:**
- Modify: `python/ftrace_expand_refs.py`
- Modify: `python/ftrace_semantic.py`

### Step 5.1: Update ftrace_expand_refs.py

- [ ] **Modify `main()` in `ftrace_expand_refs.py` (line 81)**

Replace line 81:

```python
    expanded = expand_refs(data["slice"], data["refIndex"])
```

With:

```python
    root_key = "slice" if "slice" in data else "trace"
    expanded = expand_refs(data[root_key], data["refIndex"])
```

### Step 5.2: Update ftrace_semantic.py

- [ ] **Modify `main()` in `ftrace_semantic.py` (lines 888-892)**

Replace:

```python
    if args.input:
        with open(args.input) as f:
            tree = json.load(f)
    else:
        tree = json.load(sys.stdin)
```

With:

```python
    if args.input:
        with open(args.input) as f:
            raw = json.load(f)
    else:
        raw = json.load(sys.stdin)
    tree = raw["trace"] if "trace" in raw else raw
```

### Step 5.3: Run Python tests

- [ ] **Verify Python tests still pass**

Run: `cd python && uv run pytest tests/ -q`
Expected: All tests PASS. (Python unit tests use bare tree fixtures — not affected by envelope changes.)

### Step 5.4: Commit

- [ ] **Commit Python compatibility**

```bash
git add python/ftrace_expand_refs.py python/ftrace_semantic.py
git commit -m "feat: support trace envelope format in ftrace-expand-refs and ftrace-semantic"
```

---

## Task 6: E2E Test Updates

Update shell-based E2E tests to work with the envelope output format. The changes fall into three categories:
1. **`.trace.` prefix** — root-level jq queries need `.trace.` prefix
2. **refIndex child checks** — children are now refs; edge checks on children query refIndex
3. **expand-refs before slice** — `ftrace-slice` operates on bare trees, so add an expand-refs step

**Files:**
- Modify: `test-fixtures/tests/test_xtrace_forward.sh`
- Modify: `test-fixtures/tests/test_xtrace_exception.sh`
- Modify: `test-fixtures/tests/test_xtrace_nested_exception.sh`
- Modify: `test-fixtures/tests/test_xtrace_edges_pipeline.sh`
- Modify: `test-fixtures/tests/test_ftrace_slice.sh`

### Step 6.1: Update test_xtrace_forward.sh

- [ ] **Replace `test_xtrace_forward.sh` content (lines 12-33)**

Replace lines 12-33 with:

```bash
assert_json_field "$OUT/forward.json" '.trace.class' 'com.example.app.OrderService' \
    "root class"

assert_json_field "$OUT/forward.json" '.trace.method' 'processOrder' \
    "root method"

assert_json_contains "$OUT/forward.json" \
    '.trace.children | length > 0' \
    "has children (callees)"

assert_json_contains "$OUT/forward.json" \
    '.trace.sourceTrace | any(.calls | length > 0)' \
    "sourceTrace has call entries"

assert_json_contains "$OUT/forward.json" \
    '.trace.edges | length > 0' \
    "root node has CFG edges"

assert_json_contains "$OUT/forward.json" \
    '.trace.edges | all(has("fromBlock") and has("toBlock"))' \
    "edges have fromBlock and toBlock"

assert_json_contains "$OUT/forward.json" \
    '.refIndex | length >= 0' \
    "has refIndex"
```

### Step 6.2: Update test_xtrace_exception.sh

- [ ] **Replace root-level queries in `test_xtrace_exception.sh` (lines 12-53)**

Replace lines 12-53 with:

```bash
assert_json_field "$OUT/exception.json" '.trace.method' 'handleException' \
    "method name"

assert_json_contains "$OUT/exception.json" \
    '.trace.traps | length == 2' \
    "has 2 traps (catch + finally)"

assert_json_contains "$OUT/exception.json" \
    '.trace.traps[] | select(.type | contains("RuntimeException")) | .handlerBlocks | length == 4' \
    "RuntimeException handler has 4 blocks (excludes method return)"

assert_json_contains "$OUT/exception.json" \
    '.trace.traps[] | select(.type | contains("Throwable")) | .handlerBlocks | length == 2' \
    "Throwable (finally) handler has 2 blocks (exception-path + inlined normal-path)"

assert_json_contains "$OUT/exception.json" \
    '.trace.traps[] | select(.type | contains("Throwable")) | .coveredBlocks | length > 5' \
    "Throwable (finally) trap covers multiple blocks"

# Gap-fill: intermediate blocks (B3, B5) must appear in RuntimeException coveredBlocks
assert_json_contains "$OUT/exception.json" \
    '.trace.traps[] | select(.type | contains("RuntimeException")) | .coveredBlocks | index("B3")' \
    "gap-fill: B3 (intermediate L9) in RuntimeException coveredBlocks"

assert_json_contains "$OUT/exception.json" \
    '.trace.traps[] | select(.type | contains("RuntimeException")) | .coveredBlocks | index("B5")' \
    "gap-fill: B5 (intermediate L9) in RuntimeException coveredBlocks"

# Normal-path finally (B13) must NOT be in any trap's coveredBlocks
assert_json_contains "$OUT/exception.json" \
    '[.trace.traps[].coveredBlocks[] | select(. == "B13")] | length == 0' \
    "B13 (normal-path finally) not in any coveredBlocks"

# B13 (inlined finally) should be in Throwable's handlerBlocks
assert_json_contains "$OUT/exception.json" \
    '.trace.traps[] | select(.type | contains("Throwable")) | .handlerBlocks | index("B13")' \
    "B13 (inlined finally) in Throwable handlerBlocks"

# B0 (entry block L6) should be in a trap's coveredBlocks
assert_json_contains "$OUT/exception.json" \
    '[.trace.traps[].coveredBlocks[] | select(. == "B0")] | length > 0' \
    "B0 (entry block) in coveredBlocks via gap-fill"
```

### Step 6.3: Update test_xtrace_nested_exception.sh

- [ ] **Replace root-level queries in `test_xtrace_nested_exception.sh` (lines 12-28)**

Replace lines 12-28 with:

```bash
assert_json_field "$OUT/nested.json" '.trace.method' 'nestedHandle' \
    "method name"

assert_json_contains "$OUT/nested.json" \
    '.trace.traps | length == 2' \
    "has exactly 2 traps (inner + outer)"

# Verify inner catch: 6 handler blocks (excludes normal-flow exit B9 and method return B16)
assert_json_contains "$OUT/nested.json" \
    '.trace.traps[] | select(.type | contains("java.lang.Exception")) | .handlerBlocks | length == 6' \
    "inner Exception handler has 6 blocks (excludes merge points)"

# Verify outer catch: 1 handler block (excludes method return B16)
assert_json_contains "$OUT/nested.json" \
    '.trace.traps[] | select(.type | contains("RuntimeException")) | .handlerBlocks | length == 1' \
    "outer RuntimeException handler has 1 block (excludes method return)"
```

### Step 6.4: Update test_xtrace_edges_pipeline.sh

- [ ] **Replace forward trace section in `test_xtrace_edges_pipeline.sh` (lines 16-39)**

Replace lines 16-39 with:

```bash
assert_json_contains "$OUT/edges_fwd.json" \
    '.trace.edges | length > 0' \
    "forward: root has edges"

assert_json_contains "$OUT/edges_fwd.json" \
    '.trace.edges[] | select(.label == "T" or .label == "F") | .fromBlock' \
    "forward: has branch-labeled edges (T/F)"

assert_json_contains "$OUT/edges_fwd.json" \
    '.refIndex | to_entries[] | select(.value.edges | length > 0) | .value.method' \
    "forward: refIndex methods have edges"

# ── Forward trace: edges survive semantic transform ──

cd "$REPO_ROOT/python"
uv run ftrace-expand-refs --input "$OUT/edges_fwd.json" --output "$OUT/edges_expanded.json"
uv run ftrace-semantic --input "$OUT/edges_expanded.json" --output "$OUT/edges_semantic.json"

assert_json_contains "$OUT/edges_semantic.json" \
    '.edges | length > 0' \
    "semantic: has intra-method edges"

assert_json_contains "$OUT/edges_semantic.json" \
    '.edges[] | select(.branch == "T" or .branch == "F") | .from' \
    "semantic: branch edges preserved"

# ── Forward trace: edges appear in DOT output ──

uv run ftrace-to-dot --input "$OUT/edges_semantic.json" --output "$OUT/edges.dot"
```

Note: the semantic section now runs expand-refs first to get a bare tree before semantic transform. The DOT and backward sections (lines 45-65) remain unchanged.

### Step 6.5: Update test_ftrace_slice.sh

- [ ] **Replace `test_ftrace_slice.sh` content**

The full pipeline changes from `xtrace → slice → expand-refs` to `xtrace → expand-refs → slice → expand-refs` because `ftrace-slice` requires a bare tree (it walks `children`, not `refIndex`).

Replace lines 9-17 with:

```bash
# Generate a trace that has refs, then expand to get a bare tree for slicing
$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.ComplexService --from-line "$COMPLEX_LINE" \
  --output "$OUT/complex_envelope.json"

cd "$REPO_ROOT/python"
uv run ftrace-expand-refs --input "$OUT/complex_envelope.json" \
  --output "$OUT/complex.json"

# Slice out handleException (now outputs SlicedTrace)
uv run ftrace-slice --input "$OUT/complex.json" \
```

Replace lines 58-63 (piped pipeline) with:

```bash
# Fully piped: cat | expand-refs | slice | expand-refs | semantic | to-dot (all stdin/stdout)
cat "$OUT/complex_envelope.json" \
  | uv run ftrace-expand-refs \
  | uv run ftrace-slice --query '.children[] | select(.method == "handleException")' \
  | uv run ftrace-expand-refs \
  | uv run ftrace-semantic \
  | uv run ftrace-to-dot > "$OUT/piped.dot"
```

Replace lines 71-77 (e2e piped pipeline) with:

```bash
# End-to-end piped: xtrace | expand-refs | slice | expand-refs | semantic | to-dot
$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.ComplexService --from-line "$COMPLEX_LINE" \
  | uv run ftrace-expand-refs \
  | uv run ftrace-slice --query '.children[] | select(.method == "handleException")' \
  | uv run ftrace-expand-refs \
  | uv run ftrace-semantic \
  | uv run ftrace-to-dot > "$OUT/e2e-piped.dot"
```

The `cd "$REPO_ROOT/python"` is already at line 14 in the original. After the rewrite, ensure it appears before the first `uv run` call.

### Step 6.6: Run E2E tests

- [ ] **Run the full E2E suite**

Run: `cd /Users/asgupta/code/java-bytecode-tools && test-fixtures/run-e2e.sh`
Expected: All tests PASS. If any fail, debug by examining the JSON output files directly.

### Step 6.7: Commit

- [ ] **Commit E2E updates**

```bash
git add test-fixtures/tests/test_xtrace_forward.sh \
        test-fixtures/tests/test_xtrace_exception.sh \
        test-fixtures/tests/test_xtrace_nested_exception.sh \
        test-fixtures/tests/test_xtrace_edges_pipeline.sh \
        test-fixtures/tests/test_ftrace_slice.sh
git commit -m "test: update E2E tests for ref-by-default envelope output format"
```

---

## Verification Checklist

After all tasks are complete:

- [ ] `cd java && mvn test -q` — all Java tests pass
- [ ] `cd python && uv run pytest tests/ -q` — all Python tests pass
- [ ] `test-fixtures/run-e2e.sh` — all E2E tests pass
- [ ] `git log --oneline` — 6 clean commits, one per task
- [ ] `ForwardTracer.java` has no `buildForwardNode` method
- [ ] `ForwardTracer.java` has no `globalVisited` field or local variable
- [ ] Output of `xtrace --from` is an envelope: `{"trace": {...}, "refIndex": {...}}`
- [ ] `ftrace-expand-refs` accepts both `slice` and `trace` envelope keys
- [ ] `ftrace-semantic` accepts both envelope and bare tree input
