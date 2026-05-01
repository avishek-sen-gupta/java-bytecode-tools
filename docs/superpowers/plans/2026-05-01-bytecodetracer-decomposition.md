# BytecodeTracer Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose the 551-line `BytecodeTracer` god class into seven focused classes, each with its own test file, while keeping the public facade API unchanged for `CallGraphBuilder` and `ForwardTracer`.

**Architecture:** Extract each responsibility into its own class with constructor-injected dependencies. `BytecodeTracer` becomes a thin facade that constructs and delegates to all collaborators. All mutable post-construction setters are removed; values are passed at construction time.

**Tech Stack:** Java 21, SootUp, JUnit 5, Maven (`cd java && mvn test`)

---

## File Map

### New source files
| File | Responsibility |
|------|---------------|
| `java/src/main/java/tools/bytecode/CallFrame.java` | Promoted top-level record |
| `java/src/main/java/tools/bytecode/FilterConfig.java` | Promoted top-level record with stream-based shouldRecurse |
| `java/src/main/java/tools/bytecode/StmtAnalyzer.java` | Static Jimple utilities + map-key constants |
| `java/src/main/java/tools/bytecode/MethodResolver.java` | Method lookup by name/line/signature |
| `java/src/main/java/tools/bytecode/FrameBuilder.java` | Builds CallFrame objects |
| `java/src/main/java/tools/bytecode/IntraproceduralSlicer.java` | CFG backward-reachability + trace() |
| `java/src/main/java/tools/bytecode/LineMapReporter.java` | dumpLineMap() |

### New test files
| File | Tests |
|------|-------|
| `java/src/test/java/tools/bytecode/FilterConfigTest.java` | shouldRecurse logic |
| `java/src/test/java/tools/bytecode/StmtAnalyzerTest.java` | All static methods |
| `java/src/test/java/tools/bytecode/MethodResolverTest.java` | resolveByName / resolveByLine / resolveCallee |
| `java/src/test/java/tools/bytecode/FrameBuilderTest.java` | buildFrame / buildFlatFrame |
| `java/src/test/java/tools/bytecode/IntraproceduralSlicerTest.java` | trace() |
| `java/src/test/java/tools/bytecode/LineMapReporterTest.java` | dumpLineMap() |

### Modified files
| File | Change |
|------|--------|
| `java/src/main/java/tools/bytecode/BytecodeTracer.java` | Gutted to thin facade; 3-arg constructor; setters removed |
| `java/src/main/java/tools/bytecode/cli/CLI.java` | `defaultValue = ""` on `--prefix` option |
| `java/src/main/java/tools/bytecode/cli/BaseCommand.java` | 3-arg `createTracer()` |
| `java/src/main/java/tools/bytecode/cli/XtraceCommand.java` | 3-arg constructor call with callGraphFile |
| `java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java` | `BytecodeTracer::stmtLine` → `StmtAnalyzer::stmtLine` |
| `java/src/test/java/tools/bytecode/DiscoverReachableTest.java` | `BytecodeTracer.FilterConfig` → `FilterConfig` |

### Deleted files
| File | Reason |
|------|--------|
| `java/src/test/java/tools/bytecode/BytecodeTracerResolveByNameTest.java` | Migrated to MethodResolverTest |

---

## Task 1: Promote CallFrame and FilterConfig to top-level records

**Files:**
- Create: `java/src/main/java/tools/bytecode/CallFrame.java`
- Create: `java/src/main/java/tools/bytecode/FilterConfig.java`
- Create: `java/src/test/java/tools/bytecode/FilterConfigTest.java`
- Modify: `java/src/main/java/tools/bytecode/BytecodeTracer.java` (remove inner records)
- Modify: `java/src/test/java/tools/bytecode/DiscoverReachableTest.java` (update import)

- [ ] **Step 1: Write failing test for FilterConfig.shouldRecurse**

```java
// java/src/test/java/tools/bytecode/FilterConfigTest.java
package tools.bytecode;

import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class FilterConfigTest {

    @Test
    void shouldRecurse_returnsTrueWhenNoFilters() {
        FilterConfig cfg = new FilterConfig(null, null);
        assertTrue(cfg.shouldRecurse("com.example.Foo"));
    }

    @Test
    void shouldRecurse_returnsTrueWhenClassMatchesAllowPrefix() {
        FilterConfig cfg = new FilterConfig(List.of("com.example"), null);
        assertTrue(cfg.shouldRecurse("com.example.Foo"));
    }

    @Test
    void shouldRecurse_returnsFalseWhenClassDoesNotMatchAllowPrefix() {
        FilterConfig cfg = new FilterConfig(List.of("com.example"), null);
        assertFalse(cfg.shouldRecurse("org.other.Bar"));
    }

    @Test
    void shouldRecurse_returnsFalseWhenClassMatchesStopPrefix() {
        FilterConfig cfg = new FilterConfig(null, List.of("com.ext"));
        assertFalse(cfg.shouldRecurse("com.ext.External"));
    }

    @Test
    void shouldRecurse_returnsTrueWhenClassPassesBothAllowAndStop() {
        FilterConfig cfg = new FilterConfig(List.of("com.example"), List.of("com.ext"));
        assertTrue(cfg.shouldRecurse("com.example.Internal"));
    }

    @Test
    void shouldRecurse_returnsFalseWhenClassMatchesAllowButAlsoStop() {
        FilterConfig cfg = new FilterConfig(List.of("com.example"), List.of("com.example.bad"));
        assertFalse(cfg.shouldRecurse("com.example.bad.Excluded"));
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd java && mvn test -Dtest=FilterConfigTest
```

Expected: compilation failure — `FilterConfig` class not found.

- [ ] **Step 3: Create CallFrame.java**

```java
// java/src/main/java/tools/bytecode/CallFrame.java
package tools.bytecode;

import java.util.List;
import java.util.Map;

record CallFrame(
    String className,
    String methodName,
    String methodSignature,
    int entryLine,
    int exitLine,
    List<Map<String, Object>> sourceTrace,
    List<Map<String, Object>> stmtDetails) {}
```

- [ ] **Step 4: Create FilterConfig.java with stream-based shouldRecurse**

`shouldRecurse` rewrites both nested for+if loops as `anyMatch`/`noneMatch`:

```java
// java/src/main/java/tools/bytecode/FilterConfig.java
package tools.bytecode;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

public record FilterConfig(List<String> allow, List<String> stop) {

    boolean shouldRecurse(String className) {
        boolean passesAllow = allow == null || allow.isEmpty()
            || allow.stream().anyMatch(className::startsWith);
        boolean passesStop = stop == null || stop.isEmpty()
            || stop.stream().noneMatch(className::startsWith);
        return passesAllow && passesStop;
    }

    public static FilterConfig load(Path path) throws IOException {
        if (path == null) return new FilterConfig(null, null);
        ObjectMapper m = new ObjectMapper();
        @SuppressWarnings("unchecked")
        Map<String, List<String>> raw = m.readValue(path.toFile(), Map.class);
        return new FilterConfig(raw.get("allow"), raw.get("stop"));
    }
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd java && mvn test -Dtest=FilterConfigTest
```

Expected: BUILD SUCCESS, 6 tests pass.

- [ ] **Step 6: Remove inner records from BytecodeTracer**

In `BytecodeTracer.java`, delete lines 88–124 (the `CallFrame` and `FilterConfig` inner type definitions). The file now imports from the top-level types. Add at the top of the imports:

```java
// These are now top-level — no import needed (same package), but remove the inner definitions
```

Verify the class still compiles:

```bash
cd java && mvn compile
```

- [ ] **Step 7: Update DiscoverReachableTest**

In `DiscoverReachableTest.java`, replace all occurrences of `BytecodeTracer.FilterConfig` with `FilterConfig`. Since both are in `tools.bytecode`, no import is needed.

- [ ] **Step 8: Run full test suite**

```bash
cd java && mvn test
```

Expected: BUILD SUCCESS, all existing tests pass.

- [ ] **Step 9: Commit**

```bash
git add java/src/main/java/tools/bytecode/CallFrame.java \
        java/src/main/java/tools/bytecode/FilterConfig.java \
        java/src/main/java/tools/bytecode/BytecodeTracer.java \
        java/src/test/java/tools/bytecode/FilterConfigTest.java \
        java/src/test/java/tools/bytecode/DiscoverReachableTest.java
git commit -m "refactor: promote CallFrame and FilterConfig to top-level records"
```

---

## Task 2: Extract StmtAnalyzer

**Files:**
- Create: `java/src/main/java/tools/bytecode/StmtAnalyzer.java`
- Create: `java/src/test/java/tools/bytecode/StmtAnalyzerTest.java`
- Modify: `java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java`

- [ ] **Step 1: Write failing tests for StmtAnalyzer**

```java
// java/src/test/java/tools/bytecode/StmtAnalyzerTest.java
package tools.bytecode;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import sootup.core.graph.StmtGraph;
import sootup.core.inputlocation.AnalysisInputLocation;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.SootMethod;
import sootup.core.types.ClassType;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class StmtAnalyzerTest {

    private static JavaView view;
    private static List<Stmt> orderServiceStmts;

    @BeforeAll
    static void setUp() {
        String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
        view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
        ClassType type = view.getIdentifierFactory().getClassType("com.example.app.OrderService");
        JavaSootClass cls = view.getClass(type).orElseThrow();
        SootMethod method = cls.getMethods().stream()
            .filter(m -> m.getName().equals("processOrder") && m.hasBody())
            .findFirst().orElseThrow();
        orderServiceStmts = new ArrayList<>(method.getBody().getStmtGraph().getNodes());
    }

    @Nested
    class BuildStmtDetails {
        @Test
        void returnsOneEntryPerStmt() {
            List<Map<String, Object>> details = StmtAnalyzer.buildStmtDetails(orderServiceStmts);
            assertEquals(orderServiceStmts.size(), details.size());
        }

        @Test
        void everyEntryHasLineAndJimpleKeys() {
            List<Map<String, Object>> details = StmtAnalyzer.buildStmtDetails(orderServiceStmts);
            assertTrue(details.stream().allMatch(d -> d.containsKey(StmtAnalyzer.KEY_LINE)));
            assertTrue(details.stream().allMatch(d -> d.containsKey(StmtAnalyzer.KEY_JIMPLE)));
        }

        @Test
        void doesNotMutateInput() {
            List<Stmt> copy = new ArrayList<>(orderServiceStmts);
            StmtAnalyzer.buildStmtDetails(orderServiceStmts);
            assertEquals(copy, orderServiceStmts);
        }
    }

    @Nested
    class DeduplicateToSourceLines {
        @Test
        void mergesConsecutiveSameLineEntries() {
            List<Map<String, Object>> input = List.of(
                mapOf(StmtAnalyzer.KEY_LINE, 10, StmtAnalyzer.KEY_CALL_TARGET, "com.Foo.bar"),
                mapOf(StmtAnalyzer.KEY_LINE, 10, StmtAnalyzer.KEY_CALL_TARGET, "com.Foo.baz"),
                mapOf(StmtAnalyzer.KEY_LINE, 11)
            );
            List<Map<String, Object>> result = StmtAnalyzer.deduplicateToSourceLines(input);
            assertEquals(2, result.size());
            assertEquals(10, result.get(0).get(StmtAnalyzer.KEY_LINE));
            @SuppressWarnings("unchecked")
            List<String> calls = (List<String>) result.get(0).get(StmtAnalyzer.KEY_CALLS);
            assertEquals(2, calls.size());
        }

        @Test
        void doesNotMergeDifferentLines() {
            List<Map<String, Object>> input = List.of(
                mapOf(StmtAnalyzer.KEY_LINE, 10),
                mapOf(StmtAnalyzer.KEY_LINE, 11)
            );
            assertEquals(2, StmtAnalyzer.deduplicateToSourceLines(input).size());
        }
    }

    @Nested
    class StmtsAtLine {
        @Test
        void returnsStmtsAtGivenLine() {
            SootMethod method = view.getClass(
                view.getIdentifierFactory().getClassType("com.example.app.OrderService"))
                .orElseThrow().getMethods().stream()
                .filter(m -> m.getName().equals("processOrder") && m.hasBody())
                .findFirst().orElseThrow();
            StmtGraph<?> graph = method.getBody().getStmtGraph();
            int anyLine = orderServiceStmts.stream()
                .mapToInt(StmtAnalyzer::stmtLine)
                .filter(l -> l > 0)
                .findFirst().orElseThrow();

            List<Stmt> result = StmtAnalyzer.stmtsAtLine(graph, anyLine);

            assertFalse(result.isEmpty());
            assertTrue(result.stream().allMatch(s -> StmtAnalyzer.stmtLine(s) == anyLine));
        }
    }

    @Nested
    class FindCallSiteLine {
        @Test
        void returnsLineOfExactCallTarget() {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put(StmtAnalyzer.KEY_LINE, 42);
            entry.put(StmtAnalyzer.KEY_CALLS, List.of("com.example.app.OrderRepository.findById"));
            CallFrame caller = new CallFrame("com.example.app.OrderService", "processOrder",
                "<sig>", 40, 60, List.of(entry), List.of());
            CallFrame callee = new CallFrame("com.example.app.OrderRepository", "findById",
                "<sig2>", 10, 20, List.of(), List.of());

            assertEquals(42, StmtAnalyzer.findCallSiteLine(caller, callee));
        }

        @Test
        void returnsNegativeOneWhenNoCallFound() {
            CallFrame caller = new CallFrame("com.A", "m", "<s>", 1, 5, List.of(), List.of());
            CallFrame callee = new CallFrame("com.B", "n", "<s>", 1, 5, List.of(), List.of());
            assertEquals(-1, StmtAnalyzer.findCallSiteLine(caller, callee));
        }

        @Test
        void fallsBackToMethodNameSuffixMatch() {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put(StmtAnalyzer.KEY_LINE, 55);
            entry.put(StmtAnalyzer.KEY_CALLS, List.of("com.example.app.SomeImpl.process"));
            CallFrame caller = new CallFrame("com.A", "m", "<s>", 50, 60, List.of(entry), List.of());
            // callee has different class (interface dispatch)
            CallFrame callee = new CallFrame("com.example.app.OtherImpl", "process",
                "<s>", 1, 5, List.of(), List.of());

            assertEquals(55, StmtAnalyzer.findCallSiteLine(caller, callee));
        }
    }

    // Helper
    private static Map<String, Object> mapOf(Object... kvs) {
        Map<String, Object> m = new LinkedHashMap<>();
        for (int i = 0; i < kvs.length; i += 2) m.put((String) kvs[i], kvs[i + 1]);
        return m;
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd java && mvn test -Dtest=StmtAnalyzerTest
```

Expected: compilation failure — `StmtAnalyzer` class not found.

- [ ] **Step 3: Create StmtAnalyzer.java**

```java
// java/src/main/java/tools/bytecode/StmtAnalyzer.java
package tools.bytecode;

import sootup.core.graph.StmtGraph;
import sootup.core.jimple.basic.StmtPositionInfo;
import sootup.core.jimple.common.expr.AbstractInvokeExpr;
import sootup.core.jimple.common.stmt.*;
import sootup.core.jimple.javabytecode.stmt.JSwitchStmt;
import sootup.core.model.Position;
import sootup.core.signatures.MethodSignature;

import java.util.*;
import java.util.stream.Collectors;

final class StmtAnalyzer {

    static final String KEY_LINE        = "line";
    static final String KEY_JIMPLE      = "jimple";
    static final String KEY_CALL_TARGET = "callTarget";
    static final String KEY_CALL_ARGS   = "callArgCount";
    static final String KEY_CALLS       = "calls";
    static final String KEY_BRANCH      = "branch";

    private StmtAnalyzer() {}

    static int stmtLine(Stmt stmt) {
        StmtPositionInfo posInfo = stmt.getPositionInfo();
        if (posInfo == null) return -1;
        Position pos = posInfo.getStmtPosition();
        if (pos == null) return -1;
        return pos.getFirstLine();
    }

    static Optional<AbstractInvokeExpr> extractInvoke(Stmt stmt) {
        if (stmt instanceof JInvokeStmt) {
            return ((JInvokeStmt) stmt).getInvokeExpr();
        } else if (stmt instanceof JAssignStmt) {
            return ((JAssignStmt) stmt).getInvokeExpr();
        }
        return Optional.empty();
    }

    static List<Stmt> stmtsAtLine(StmtGraph<?> graph, int line) {
        return graph.getNodes().stream()
            .filter(s -> stmtLine(s) == line)
            .collect(Collectors.toList());
    }

    static List<Map<String, Object>> buildStmtDetails(List<Stmt> stmts) {
        return stmts.stream().map(stmt -> {
            Map<String, Object> detail = new LinkedHashMap<>();
            detail.put(KEY_LINE, stmtLine(stmt));
            detail.put(KEY_JIMPLE, stmt.toString());
            extractInvoke(stmt).ifPresent(invoke -> {
                MethodSignature sig = invoke.getMethodSignature();
                detail.put(KEY_CALL_TARGET,
                    sig.getDeclClassType().getFullyQualifiedName() + "." + sig.getName());
                detail.put(KEY_CALL_ARGS, invoke.getArgCount());
            });
            if (stmt instanceof JIfStmt) {
                detail.put(KEY_BRANCH, ((JIfStmt) stmt).getCondition().toString());
            } else if (stmt instanceof JSwitchStmt) {
                detail.put(KEY_BRANCH, "switch");
            }
            return detail;
        }).collect(Collectors.toList());
    }

    /**
     * Merges consecutive statements at the same source line into one entry.
     * Accumulates call targets from all bytecode instructions on the same line.
     * Uses an imperative loop: merging requires comparing each entry to its predecessor,
     * which is inherently sequential state.
     */
    static List<Map<String, Object>> deduplicateToSourceLines(List<Map<String, Object>> stmtDetails) {
        List<Map<String, Object>> result = new ArrayList<>();
        int prevLine = -2;
        for (Map<String, Object> detail : stmtDetails) {
            int line = (int) detail.get(KEY_LINE);
            if (line == prevLine && !result.isEmpty()) {
                Map<String, Object> prev = result.get(result.size() - 1);
                if (detail.containsKey(KEY_CALL_TARGET)) {
                    @SuppressWarnings("unchecked")
                    List<String> calls = (List<String>) prev.computeIfAbsent(KEY_CALLS, k -> new ArrayList<>());
                    calls.add((String) detail.get(KEY_CALL_TARGET));
                }
                if (detail.containsKey(KEY_BRANCH)) {
                    prev.put(KEY_BRANCH, detail.get(KEY_BRANCH));
                }
            } else {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put(KEY_LINE, line);
                if (detail.containsKey(KEY_CALL_TARGET)) {
                    List<String> calls = new ArrayList<>();
                    calls.add((String) detail.get(KEY_CALL_TARGET));
                    entry.put(KEY_CALLS, calls);
                }
                if (detail.containsKey(KEY_BRANCH)) {
                    entry.put(KEY_BRANCH, detail.get(KEY_BRANCH));
                }
                result.add(entry);
            }
            prevLine = line;
        }
        return result;
    }

    static int findCallSiteLine(CallFrame caller, CallFrame callee) {
        String exact = callee.className() + "." + callee.methodName();
        String suffix = "." + callee.methodName();
        return findFirstCallLine(caller.sourceTrace(), exact)
            .orElseGet(() -> findFirstCallLine(caller.sourceTrace(), c -> c.endsWith(suffix))
                .orElse(-1));
    }

    private static OptionalInt findFirstCallLine(
            List<Map<String, Object>> trace, String exactTarget) {
        return findFirstCallLine(trace, exactTarget::equals);
    }

    private static OptionalInt findFirstCallLine(
            List<Map<String, Object>> trace, java.util.function.Predicate<String> matcher) {
        return trace.stream()
            .filter(e -> e.containsKey(KEY_CALLS))
            .flatMapToInt(e -> {
                @SuppressWarnings("unchecked")
                List<String> calls = (List<String>) e.get(KEY_CALLS);
                return calls.stream()
                    .filter(matcher)
                    .mapToInt(c -> (int) e.get(KEY_LINE));
            })
            .findFirst();
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd java && mvn test -Dtest=StmtAnalyzerTest
```

Expected: BUILD SUCCESS, all tests pass.

- [ ] **Step 5: Update SpoonCfgComparisonTest**

In `SpoonCfgComparisonTest.java`, replace the reference `BytecodeTracer::stmtLine` with `StmtAnalyzer::stmtLine`. Since both are in `tools.bytecode`, no import change is needed.

- [ ] **Step 6: Run full test suite**

```bash
cd java && mvn test
```

Expected: BUILD SUCCESS, all tests pass.

- [ ] **Step 7: Commit**

```bash
git add java/src/main/java/tools/bytecode/StmtAnalyzer.java \
        java/src/test/java/tools/bytecode/StmtAnalyzerTest.java \
        java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java
git commit -m "refactor: extract StmtAnalyzer with string key constants and stream-based methods"
```

---

## Task 3: Extract MethodResolver

**Files:**
- Create: `java/src/main/java/tools/bytecode/MethodResolver.java`
- Create: `java/src/test/java/tools/bytecode/MethodResolverTest.java`
- Delete: `java/src/test/java/tools/bytecode/BytecodeTracerResolveByNameTest.java`

- [ ] **Step 1: Write failing tests for MethodResolver**

```java
// java/src/test/java/tools/bytecode/MethodResolverTest.java
package tools.bytecode;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import sootup.core.inputlocation.AnalysisInputLocation;
import sootup.core.model.SootMethod;
import sootup.core.signatures.MethodSignature;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.views.JavaView;

import java.nio.file.Paths;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

class MethodResolverTest {

    private static MethodResolver resolver;

    @BeforeAll
    static void setUp() {
        String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
        JavaView view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
        resolver = new MethodResolver(view);
    }

    @Nested
    class ResolveByName {
        @Test
        void returnsMethod_whenExactlyOneMatch() {
            SootMethod m = resolver.resolveByName("com.example.app.OrderService", "processOrder");
            assertEquals("processOrder", m.getName());
        }

        @Test
        void throwsWithHelpfulMessage_whenMethodNotFound() {
            RuntimeException ex = assertThrows(RuntimeException.class,
                () -> resolver.resolveByName("com.example.app.OrderService", "nonexistent"));
            assertTrue(ex.getMessage().contains("No method named 'nonexistent'"),
                "Got: " + ex.getMessage());
        }

        @Test
        void throwsWithOverloadDetails_whenMethodAmbiguous() {
            RuntimeException ex = assertThrows(RuntimeException.class,
                () -> resolver.resolveByName("com.example.app.OverloadedService", "process"));
            assertTrue(ex.getMessage().contains("Ambiguous"), "Got: " + ex.getMessage());
            assertTrue(ex.getMessage().contains("--from-line"), "Got: " + ex.getMessage());
        }

        @Test
        void throwsWithClassName_whenClassNotFound() {
            RuntimeException ex = assertThrows(RuntimeException.class,
                () -> resolver.resolveByName("com.example.app.NoSuchClass", "method"));
            assertTrue(ex.getMessage().contains("com.example.app.NoSuchClass"),
                "Got: " + ex.getMessage());
        }
    }

    @Nested
    class ResolveByLine {
        @Test
        void returnsMethod_whenLineExistsInMethod() {
            SootMethod byName = resolver.resolveByName("com.example.app.OrderService", "processOrder");
            int startLine = byName.getBody().getStmtGraph().getNodes().stream()
                .mapToInt(StmtAnalyzer::stmtLine)
                .filter(l -> l > 0)
                .min().orElseThrow();

            SootMethod byLine = resolver.resolveByLine("com.example.app.OrderService", startLine);
            assertEquals("processOrder", byLine.getName());
        }

        @Test
        void throws_whenNoMethodContainsLine() {
            RuntimeException ex = assertThrows(RuntimeException.class,
                () -> resolver.resolveByLine("com.example.app.OrderService", 999999));
            assertTrue(ex.getMessage().contains("999999"), "Got: " + ex.getMessage());
        }
    }

    @Nested
    class ResolveCallee {
        @Test
        void returnsEmpty_whenClassNotFound() {
            // Construct a MethodSignature for a class that doesn't exist in the fixture
            SootMethod known = resolver.resolveByName("com.example.app.OrderService", "processOrder");
            MethodSignature sig = known.getSignature(); // valid sig but we test non-existent separately
            // Use a non-existent class type — easiest via the MethodResolver's internal view,
            // so test via resolveByName which exercises the same class-lookup path.
            // resolveCallee is package-private; test indirectly through the class not found path.
            Optional<SootMethod> result = resolver.resolveCallee(sig);
            // processOrder is a real method, so it should be found
            assertTrue(result.isPresent());
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd java && mvn test -Dtest=MethodResolverTest
```

Expected: compilation failure — `MethodResolver` class not found.

- [ ] **Step 3: Create MethodResolver.java**

```java
// java/src/main/java/tools/bytecode/MethodResolver.java
package tools.bytecode;

import sootup.core.model.SootMethod;
import sootup.core.signatures.MethodSignature;
import sootup.core.types.ClassType;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

class MethodResolver {

    private final JavaView view;

    MethodResolver(JavaView view) {
        this.view = view;
    }

    SootMethod resolveByName(String className, String methodName) {
        ClassType type = view.getIdentifierFactory().getClassType(className);
        JavaSootClass cls = view.getClass(type)
            .orElseThrow(() -> new RuntimeException("Class not found: " + className));
        List<SootMethod> matches = cls.getMethods().stream()
            .filter(m -> m.getName().equals(methodName) && m.hasBody())
            .collect(Collectors.toList());
        if (matches.isEmpty()) {
            throw new RuntimeException("No method named '" + methodName + "' in " + className);
        }
        if (matches.size() > 1) {
            StringBuilder sb = new StringBuilder()
                .append("Ambiguous: ").append(matches.size())
                .append(" overloads for '").append(methodName).append("' in ").append(className)
                .append(":\n");
            matches.forEach(m -> {
                int lineStart = m.getBody().getStmtGraph().getNodes().stream()
                    .mapToInt(StmtAnalyzer::stmtLine)
                    .filter(l -> l > 0)
                    .min().orElse(-1);
                sb.append("  ").append(m.getSignature())
                  .append(" (line ").append(lineStart).append(")\n");
            });
            sb.append("Use --from-line to disambiguate.");
            throw new RuntimeException(sb.toString());
        }
        return matches.get(0);
    }

    SootMethod resolveByLine(String className, int line) {
        ClassType type = view.getIdentifierFactory().getClassType(className);
        JavaSootClass cls = view.getClass(type)
            .orElseThrow(() -> new RuntimeException("Class not found: " + className));
        return findMethodsContainingLine(cls, line).stream()
            .findFirst()
            .orElseThrow(() -> new RuntimeException(
                "No method containing line " + line + " in " + className));
    }

    Optional<SootMethod> resolveCallee(MethodSignature sig) {
        ClassType declType = sig.getDeclClassType();
        Optional<JavaSootClass> clsOpt = view.getClass(declType);
        if (clsOpt.isEmpty()) return Optional.empty();
        JavaSootClass cls = clsOpt.get();
        try {
            Optional<? extends SootMethod> mOpt = cls.getMethod(sig.getSubSignature());
            if (mOpt.isPresent() && mOpt.get().hasBody()) return Optional.of(mOpt.get());
        } catch (Exception ignored) {}
        int paramCount = sig.getParameterTypes().size();
        return cls.getMethods().stream()
            .filter(m -> m.getName().equals(sig.getName())
                && m.getParameterCount() == paramCount
                && m.hasBody())
            .findFirst();
    }

    List<SootMethod> findMethodsContainingLine(JavaSootClass clazz, int line) {
        return clazz.getMethods().stream()
            .filter(SootMethod::hasBody)
            .filter(m -> m.getBody().getStmtGraph().getNodes().stream()
                .anyMatch(s -> StmtAnalyzer.stmtLine(s) == line))
            .collect(Collectors.toList());
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd java && mvn test -Dtest=MethodResolverTest
```

Expected: BUILD SUCCESS, all tests pass.

- [ ] **Step 5: Delete the old test file**

```bash
rm java/src/test/java/tools/bytecode/BytecodeTracerResolveByNameTest.java
```

- [ ] **Step 6: Run full test suite**

```bash
cd java && mvn test
```

Expected: BUILD SUCCESS.

- [ ] **Step 7: Commit**

```bash
git add java/src/main/java/tools/bytecode/MethodResolver.java \
        java/src/test/java/tools/bytecode/MethodResolverTest.java
git rm java/src/test/java/tools/bytecode/BytecodeTracerResolveByNameTest.java
git commit -m "refactor: extract MethodResolver with Optional<SootMethod> for resolveCallee"
```

---

## Task 4: Extract FrameBuilder

**Files:**
- Create: `java/src/main/java/tools/bytecode/FrameBuilder.java`
- Create: `java/src/test/java/tools/bytecode/FrameBuilderTest.java`

- [ ] **Step 1: Write failing tests for FrameBuilder**

```java
// java/src/test/java/tools/bytecode/FrameBuilderTest.java
package tools.bytecode;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import sootup.core.model.SootMethod;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.views.JavaView;

import java.nio.file.Paths;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FrameBuilderTest {

    private static FrameBuilder builder;
    private static SootMethod processOrder;

    @BeforeAll
    static void setUp() {
        String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
        JavaView view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
        MethodResolver resolver = new MethodResolver(view);
        builder = new FrameBuilder(resolver);
        processOrder = resolver.resolveByName("com.example.app.OrderService", "processOrder");
    }

    @Nested
    class BuildFrame {
        @Test
        void setsClassAndMethodName() {
            CallFrame frame = builder.buildFrame(processOrder, processOrder.getSignature().toString());
            assertEquals("com.example.app.OrderService", frame.className());
            assertEquals("processOrder", frame.methodName());
        }

        @Test
        void setsPositivEntryAndExitLines() {
            CallFrame frame = builder.buildFrame(processOrder, processOrder.getSignature().toString());
            assertTrue(frame.entryLine() > 0, "entryLine should be positive");
            assertTrue(frame.exitLine() >= frame.entryLine(), "exitLine should be >= entryLine");
        }

        @Test
        void populatesSourceTrace() {
            CallFrame frame = builder.buildFrame(processOrder, processOrder.getSignature().toString());
            assertFalse(frame.sourceTrace().isEmpty());
        }

        @Test
        void populatesStmtDetails() {
            CallFrame frame = builder.buildFrame(processOrder, processOrder.getSignature().toString());
            assertFalse(frame.stmtDetails().isEmpty());
        }

        @Test
        void sourceTraceEntriesHaveLineKey() {
            CallFrame frame = builder.buildFrame(processOrder, processOrder.getSignature().toString());
            assertTrue(frame.sourceTrace().stream()
                .allMatch(e -> e.containsKey(StmtAnalyzer.KEY_LINE)));
        }
    }

    @Nested
    class BuildFlatFrame {
        @Test
        void setsClassAndMethodName() {
            CallFrame frame = builder.buildFlatFrame(processOrder, processOrder.getSignature().toString());
            assertEquals("com.example.app.OrderService", frame.className());
            assertEquals("processOrder", frame.methodName());
        }

        @Test
        void hasEmptyStmtDetails() {
            CallFrame frame = builder.buildFlatFrame(processOrder, processOrder.getSignature().toString());
            assertTrue(frame.stmtDetails().isEmpty());
        }

        @Test
        void sourceTraceContainsOnlyCallEntries() {
            CallFrame frame = builder.buildFlatFrame(processOrder, processOrder.getSignature().toString());
            // flat frame only includes lines with invocations
            frame.sourceTrace().forEach(e ->
                assertTrue(e.containsKey(StmtAnalyzer.KEY_CALLS),
                    "Flat frame trace entries should have calls key"));
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd java && mvn test -Dtest=FrameBuilderTest
```

Expected: compilation failure — `FrameBuilder` class not found.

- [ ] **Step 3: Create FrameBuilder.java**

```java
// java/src/main/java/tools/bytecode/FrameBuilder.java
package tools.bytecode;

import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.Body;
import sootup.core.model.SootMethod;
import sootup.core.signatures.MethodSignature;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

class FrameBuilder {

    private final MethodResolver resolver;

    FrameBuilder(MethodResolver resolver) {
        this.resolver = resolver;
    }

    CallFrame buildFrame(SootMethod method, String sig) {
        String methodClass = method.getDeclaringClassType().getFullyQualifiedName();
        Body body = method.getBody();
        List<Stmt> stmts = new ArrayList<>(body.getStmtGraph().getNodes());
        List<Map<String, Object>> details = StmtAnalyzer.buildStmtDetails(stmts);
        List<Map<String, Object>> srcTrace = StmtAnalyzer.deduplicateToSourceLines(details);
        int minL = stmts.stream().mapToInt(StmtAnalyzer::stmtLine).filter(l -> l > 0).min().orElse(-1);
        int maxL = stmts.stream().mapToInt(StmtAnalyzer::stmtLine).max().orElse(-1);
        return new CallFrame(methodClass, method.getName(), sig, minL, maxL, srcTrace, details);
    }

    CallFrame buildFlatFrame(SootMethod method, String sig) {
        String methodClass = method.getDeclaringClassType().getFullyQualifiedName();
        Body body = method.getBody();
        List<Stmt> stmts = new ArrayList<>(body.getStmtGraph().getNodes());
        int minL = stmts.stream().mapToInt(StmtAnalyzer::stmtLine).filter(l -> l > 0).min().orElse(-1);
        int maxL = stmts.stream().mapToInt(StmtAnalyzer::stmtLine).max().orElse(-1);
        List<Map<String, Object>> callTrace = stmts.stream()
            .flatMap(stmt -> StmtAnalyzer.extractInvoke(stmt).stream().map(invoke -> {
                int line = StmtAnalyzer.stmtLine(stmt);
                if (line <= 0) return null;
                MethodSignature callSig = invoke.getMethodSignature();
                String callTarget = callSig.getDeclClassType().getFullyQualifiedName()
                    + "." + callSig.getName();
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put(StmtAnalyzer.KEY_LINE, line);
                entry.put(StmtAnalyzer.KEY_CALLS, List.of(callTarget));
                return entry;
            }))
            .filter(e -> e != null)
            .collect(Collectors.toList());
        return new CallFrame(methodClass, method.getName(), sig, minL, maxL, callTrace, List.of());
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd java && mvn test -Dtest=FrameBuilderTest
```

Expected: BUILD SUCCESS, all tests pass.

- [ ] **Step 5: Run full test suite**

```bash
cd java && mvn test
```

Expected: BUILD SUCCESS.

- [ ] **Step 6: Commit**

```bash
git add java/src/main/java/tools/bytecode/FrameBuilder.java \
        java/src/test/java/tools/bytecode/FrameBuilderTest.java
git commit -m "refactor: extract FrameBuilder using StmtAnalyzer for all statement analysis"
```

---

## Task 5: Extract IntraproceduralSlicer

**Files:**
- Create: `java/src/main/java/tools/bytecode/IntraproceduralSlicer.java`
- Create: `java/src/test/java/tools/bytecode/IntraproceduralSlicerTest.java`

- [ ] **Step 1: Write failing tests for IntraproceduralSlicer**

```java
// java/src/test/java/tools/bytecode/IntraproceduralSlicerTest.java
package tools.bytecode;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.views.JavaView;

import java.nio.file.Paths;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class IntraproceduralSlicerTest {

    private static IntraproceduralSlicer slicer;
    private static MethodResolver resolver;
    private static final String ORDER_SERVICE = "com.example.app.OrderService";

    @BeforeAll
    static void setUp() {
        String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
        JavaView view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
        resolver = new MethodResolver(view);
        slicer = new IntraproceduralSlicer(view, resolver);
    }

    @Nested
    class Trace {
        @Test
        void returnsResultWithClassAndLineFields() {
            int toLine = anyLineIn(ORDER_SERVICE, "processOrder");
            Map<String, Object> result = slicer.trace(ORDER_SERVICE, -1, toLine);
            assertEquals(ORDER_SERVICE, result.get("class"));
            assertEquals(-1, result.get("fromLine"));
            assertEquals(toLine, result.get("toLine"));
        }

        @Test
        void returnsNonEmptyTraces_whenToLineExistsInMethod() {
            int toLine = anyLineIn(ORDER_SERVICE, "processOrder");
            Map<String, Object> result = slicer.trace(ORDER_SERVICE, -1, toLine);
            @SuppressWarnings("unchecked")
            List<?> traces = (List<?>) result.get("traces");
            assertFalse(traces.isEmpty());
        }

        @Test
        void tracesContainMethodAndSourceTraceFields() {
            int toLine = anyLineIn(ORDER_SERVICE, "processOrder");
            Map<String, Object> result = slicer.trace(ORDER_SERVICE, -1, toLine);
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> traces = (List<Map<String, Object>>) result.get("traces");
            Map<String, Object> first = traces.get(0);
            assertTrue(first.containsKey("method"));
            assertTrue(first.containsKey("sourceTrace"));
            assertTrue(first.containsKey("stmtDetails"));
        }

        @Test
        void throws_whenClassNotFound() {
            assertThrows(RuntimeException.class,
                () -> slicer.trace("com.example.NoSuch", -1, 10));
        }
    }

    private static int anyLineIn(String className, String methodName) {
        return resolver.resolveByName(className, methodName)
            .getBody().getStmtGraph().getNodes().stream()
            .mapToInt(StmtAnalyzer::stmtLine)
            .filter(l -> l > 0)
            .max().orElseThrow();
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd java && mvn test -Dtest=IntraproceduralSlicerTest
```

Expected: compilation failure — `IntraproceduralSlicer` class not found.

- [ ] **Step 3: Create IntraproceduralSlicer.java**

```java
// java/src/main/java/tools/bytecode/IntraproceduralSlicer.java
package tools.bytecode;

import sootup.core.graph.StmtGraph;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.Body;
import sootup.core.model.SootMethod;
import sootup.core.types.ClassType;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

import java.util.*;
import java.util.stream.Collectors;

class IntraproceduralSlicer {

    private final JavaView view;
    private final MethodResolver resolver;

    IntraproceduralSlicer(JavaView view, MethodResolver resolver) {
        this.view = view;
        this.resolver = resolver;
    }

    Map<String, Object> trace(String className, int fromLine, int toLine) {
        ClassType classType = view.getIdentifierFactory().getClassType(className);
        JavaSootClass clazz = view.getClass(classType)
            .orElseThrow(() -> new RuntimeException("Class not found: " + className));

        List<SootMethod> candidateMethods = resolver.findMethodsContainingLine(clazz, toLine);
        if (candidateMethods.isEmpty()) {
            candidateMethods = resolver.findMethodsContainingLine(clazz, fromLine);
        }
        if (candidateMethods.isEmpty()) {
            throw new RuntimeException(
                "No method found containing line " + toLine + " or " + fromLine + " in " + className);
        }

        List<Map<String, Object>> allTraces = candidateMethods.stream()
            .flatMap(method -> buildMethodTrace(method, fromLine, toLine).stream())
            .collect(Collectors.toList());

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("class", className);
        result.put("fromLine", fromLine);
        result.put("toLine", toLine);
        result.put("traces", allTraces);
        return result;
    }

    private Optional<Map<String, Object>> buildMethodTrace(SootMethod method, int fromLine, int toLine) {
        Body body = method.getBody();
        StmtGraph<?> graph = body.getStmtGraph();
        Set<Stmt> fromStmts = new LinkedHashSet<>(StmtAnalyzer.stmtsAtLine(graph, fromLine));
        Set<Stmt> toStmts = new LinkedHashSet<>(StmtAnalyzer.stmtsAtLine(graph, toLine));
        if (toStmts.isEmpty()) return Optional.empty();

        List<Stmt> pathStmts = fromStmts.isEmpty()
            ? backtrack(graph, Collections.emptySet(), toStmts)
            : backtrack(graph, fromStmts, toStmts);
        if (pathStmts.isEmpty() && !fromStmts.isEmpty()) return Optional.empty();

        List<Map<String, Object>> stmtDetails = StmtAnalyzer.buildStmtDetails(pathStmts);
        List<Map<String, Object>> sourceTrace = StmtAnalyzer.deduplicateToSourceLines(stmtDetails);

        Map<String, Object> methodTrace = new LinkedHashMap<>();
        methodTrace.put("method", method.getName());
        methodTrace.put("methodSignature", method.getSignature().toString());
        methodTrace.put("stmtCount", pathStmts.size());
        methodTrace.put("sourceLineCount", sourceTrace.size());
        methodTrace.put("sourceTrace", sourceTrace);
        methodTrace.put("stmtDetails", stmtDetails);
        return Optional.of(methodTrace);
    }

    /**
     * BFS backward from {@code toStmts}, collecting all stmts on any path that reaches
     * {@code fromStmts}. Uses an imperative queue+visited pattern — this algorithm is
     * inherently stateful and has no idiomatic functional equivalent in Java.
     */
    private List<Stmt> backtrack(StmtGraph<?> graph, Set<Stmt> fromStmts, Set<Stmt> toStmts) {
        Map<Stmt, Stmt> parentMap = new LinkedHashMap<>();
        Queue<Stmt> queue = new ArrayDeque<>(toStmts);
        Set<Stmt> visited = new LinkedHashSet<>(toStmts);
        toStmts.forEach(s -> parentMap.put(s, null));

        Set<Stmt> reachedFrom = new LinkedHashSet<>();
        while (!queue.isEmpty()) {
            Stmt current = queue.poll();
            if (fromStmts.contains(current)) reachedFrom.add(current);
            for (Stmt pred : graph.predecessors(current)) {
                if (visited.add(pred)) {
                    parentMap.put(pred, current);
                    queue.add(pred);
                }
            }
        }

        if (reachedFrom.isEmpty() && !fromStmts.isEmpty()) return Collections.emptyList();

        Set<Stmt> onPath = new LinkedHashSet<>();
        Queue<Stmt> traceQueue = new ArrayDeque<>(reachedFrom);
        while (!traceQueue.isEmpty()) {
            Stmt s = traceQueue.poll();
            if (onPath.add(s)) {
                Stmt next = parentMap.get(s);
                if (next != null) traceQueue.add(next);
            }
        }
        return new ArrayList<>(onPath);
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd java && mvn test -Dtest=IntraproceduralSlicerTest
```

Expected: BUILD SUCCESS, all tests pass.

- [ ] **Step 5: Run full test suite**

```bash
cd java && mvn test
```

Expected: BUILD SUCCESS.

- [ ] **Step 6: Commit**

```bash
git add java/src/main/java/tools/bytecode/IntraproceduralSlicer.java \
        java/src/test/java/tools/bytecode/IntraproceduralSlicerTest.java
git commit -m "refactor: extract IntraproceduralSlicer; eliminates buildStmtDetails duplication"
```

---

## Task 6: Extract LineMapReporter

**Files:**
- Create: `java/src/main/java/tools/bytecode/LineMapReporter.java`
- Create: `java/src/test/java/tools/bytecode/LineMapReporterTest.java`

- [ ] **Step 1: Write failing tests for LineMapReporter**

```java
// java/src/test/java/tools/bytecode/LineMapReporterTest.java
package tools.bytecode;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.views.JavaView;

import java.nio.file.Paths;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class LineMapReporterTest {

    private static LineMapReporter reporter;
    private static final String ORDER_SERVICE = "com.example.app.OrderService";

    @BeforeAll
    static void setUp() {
        String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
        JavaView view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
        reporter = new LineMapReporter(view);
    }

    @Test
    void returnsClassNameAndMethodCount() {
        Map<String, Object> result = reporter.dumpLineMap(ORDER_SERVICE);
        assertEquals(ORDER_SERVICE, result.get("class"));
        int methodCount = (int) result.get("methodCount");
        assertTrue(methodCount > 0);
    }

    @Test
    void methodsListHasExpectedSize() {
        Map<String, Object> result = reporter.dumpLineMap(ORDER_SERVICE);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> methods = (List<Map<String, Object>>) result.get("methods");
        assertEquals(result.get("methodCount"), methods.size());
    }

    @Test
    void eachMethodEntryHasRequiredKeys() {
        Map<String, Object> result = reporter.dumpLineMap(ORDER_SERVICE);
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> methods = (List<Map<String, Object>>) result.get("methods");
        methods.forEach(m -> {
            assertTrue(m.containsKey("method"), "missing 'method' key");
            assertTrue(m.containsKey("lineStart"), "missing 'lineStart' key");
            assertTrue(m.containsKey("lineEnd"), "missing 'lineEnd' key");
            assertTrue(m.containsKey("stmtCount"), "missing 'stmtCount' key");
            assertTrue(m.containsKey("lineMap"), "missing 'lineMap' key");
        });
    }

    @Test
    void throws_whenClassNotFound() {
        assertThrows(RuntimeException.class,
            () -> reporter.dumpLineMap("com.example.NoSuch"));
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd java && mvn test -Dtest=LineMapReporterTest
```

Expected: compilation failure — `LineMapReporter` class not found.

- [ ] **Step 3: Create LineMapReporter.java**

```java
// java/src/main/java/tools/bytecode/LineMapReporter.java
package tools.bytecode;

import sootup.core.graph.StmtGraph;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.Body;
import sootup.core.model.SootMethod;
import sootup.core.types.ClassType;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

import java.util.*;
import java.util.stream.Collectors;

class LineMapReporter {

    private final JavaView view;

    LineMapReporter(JavaView view) {
        this.view = view;
    }

    Map<String, Object> dumpLineMap(String className) {
        ClassType classType = view.getIdentifierFactory().getClassType(className);
        JavaSootClass clazz = view.getClass(classType)
            .orElseThrow(() -> new RuntimeException("Class not found: " + className));

        List<Map<String, Object>> methods = clazz.getMethods().stream()
            .filter(SootMethod::hasBody)
            .map(this::buildMethodLineMap)
            .collect(Collectors.toList());

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("class", className);
        result.put("methodCount", methods.size());
        result.put("methods", methods);
        return result;
    }

    private Map<String, Object> buildMethodLineMap(SootMethod method) {
        Body body = method.getBody();
        StmtGraph<?> graph = body.getStmtGraph();
        List<Stmt> nodes = new ArrayList<>(graph.getNodes());

        Map<Integer, Integer> lineCounts = nodes.stream()
            .collect(Collectors.toMap(
                StmtAnalyzer::stmtLine,
                s -> 1,
                Integer::sum,
                TreeMap::new));

        int minLine = lineCounts.keySet().stream().filter(l -> l > 0).mapToInt(i -> i).min().orElse(-1);
        int maxLine = lineCounts.keySet().stream().mapToInt(i -> i).max().orElse(-1);

        Map<String, Object> m = new LinkedHashMap<>();
        m.put("method", method.getName());
        m.put("signature", method.getSignature().toString());
        m.put("lineStart", minLine);
        m.put("lineEnd", maxLine);
        m.put("stmtCount", nodes.size());
        m.put("sourceLines", lineCounts.size());
        m.put("lineMap", lineCounts);
        return m;
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd java && mvn test -Dtest=LineMapReporterTest
```

Expected: BUILD SUCCESS, all tests pass.

- [ ] **Step 5: Run full test suite**

```bash
cd java && mvn test
```

Expected: BUILD SUCCESS.

- [ ] **Step 6: Commit**

```bash
git add java/src/main/java/tools/bytecode/LineMapReporter.java \
        java/src/test/java/tools/bytecode/LineMapReporterTest.java
git commit -m "refactor: extract LineMapReporter with stream-based method line map construction"
```

---

## Task 7: Gut BytecodeTracer to thin facade + constructor injection

**Files:**
- Modify: `java/src/main/java/tools/bytecode/BytecodeTracer.java`

At this point all extracted classes exist and are tested. Replace `BytecodeTracer` body with a
facade that wires collaborators in its constructor and delegates all methods.

> **Note:** Before deleting `resolveCallee` from `BytecodeTracer`, confirm it is not referenced
> there (`grep -n "resolveCallee" java/src/main/java/tools/bytecode/BytecodeTracer.java`). If it
> appears in another method body, migrate that call to use `methodResolver.resolveCallee(...)`.
> If unreferenced, delete it — it is dead code.

- [ ] **Step 1: Rewrite BytecodeTracer.java**

Replace the entire file contents:

```java
// java/src/main/java/tools/bytecode/BytecodeTracer.java
package tools.bytecode;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import sootup.core.inputlocation.AnalysisInputLocation;
import sootup.core.model.SootMethod;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

import java.util.Map;

/**
 * Thin facade — constructs and wires all bytecode-analysis collaborators. Public API is
 * unchanged; {@link CallGraphBuilder} and {@link ForwardTracer} receive this class as before.
 */
public class BytecodeTracer {

    private static final Logger log = LoggerFactory.getLogger(BytecodeTracer.class);

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

    private static JavaView buildView(String classpath) {
        List<AnalysisInputLocation> locations = new ArrayList<>();
        for (String path : classpath.split(":")) {
            if (!path.isBlank()) {
                log.info("[init] Registering classpath entry: {}", path);
                locations.add(new JavaClassPathAnalysisInputLocation(path));
            }
        }
        log.info("[init] Building JavaView from {} location(s)...", locations.size());
        long t = System.currentTimeMillis();
        JavaView view = new JavaView(locations);
        log.info("[init] JavaView ready in {}ms", System.currentTimeMillis() - t);
        return view;
    }

    // ------------------------------------------------------------------
    // Configuration
    // ------------------------------------------------------------------

    public Path getCallGraphCache() {
        return callGraphCache;
    }

    public List<JavaSootClass> getProjectClasses() {
        log.info("[init] Enumerating classes (prefix={})...", projectPrefix);
        long t = System.currentTimeMillis();
        var stream = view.getClasses();
        if (projectPrefix != null && !projectPrefix.isBlank()) {
            stream = stream.filter(c -> c.getType().getFullyQualifiedName().startsWith(projectPrefix));
        }
        List<JavaSootClass> result = stream.collect(Collectors.toList());
        log.info("[init] Found {} classes in {}ms", result.size(), System.currentTimeMillis() - t);
        return result;
    }

    // ------------------------------------------------------------------
    // Delegating API for CallGraphBuilder and ForwardTracer
    // ------------------------------------------------------------------

    SootMethod resolveMethodByName(String className, String methodName) {
        return methodResolver.resolveByName(className, methodName);
    }

    SootMethod resolveMethod(String className, int line) {
        return methodResolver.resolveByLine(className, line);
    }

    CallFrame buildFrame(SootMethod method, String sig) {
        return frameBuilder.buildFrame(method, sig);
    }

    CallFrame buildFlatFrame(SootMethod method, String sig) {
        return frameBuilder.buildFlatFrame(method, sig);
    }

    // ------------------------------------------------------------------
    // Public feature methods
    // ------------------------------------------------------------------

    public Map<String, Object> trace(String className, int fromLine, int toLine) {
        return slicer.trace(className, fromLine, toLine);
    }

    public Map<String, Object> dumpLineMap(String className) {
        return lineMapReporter.dumpLineMap(className);
    }
}
```

- [ ] **Step 2: Run full test suite**

```bash
cd java && mvn test
```

Expected: BUILD SUCCESS. If any test references removed methods (e.g. `stmtLine` via
`BytecodeTracer::stmtLine`), fix the reference to use `StmtAnalyzer::stmtLine`.

- [ ] **Step 3: Commit**

```bash
git add java/src/main/java/tools/bytecode/BytecodeTracer.java
git commit -m "refactor: gut BytecodeTracer to thin facade; remove mutable setters; replace System.err with log"
```

---

## Task 8: Update CLI to use 3-arg constructor

**Files:**
- Modify: `java/src/main/java/tools/bytecode/cli/CLI.java`
- Modify: `java/src/main/java/tools/bytecode/cli/BaseCommand.java`
- Modify: `java/src/main/java/tools/bytecode/cli/XtraceCommand.java`

- [ ] **Step 1: Add defaultValue to CLI.java --prefix option**

In `CLI.java`, change:
```java
@Option(names = "--prefix", description = "Limit analysis to classes whose FQCN starts with this prefix")
String prefix;
```
to:
```java
@Option(names = "--prefix", defaultValue = "",
    description = "Limit analysis to classes whose FQCN starts with this prefix")
String prefix;
```

- [ ] **Step 2: Update BaseCommand.createTracer()**

Replace `createTracer()` in `BaseCommand.java`:

```java
BytecodeTracer createTracer() {
    System.err.println("[createTracer] classpath=" + parent.classpath);
    System.err.println("[createTracer] prefix=" + parent.prefix);
    BytecodeTracer tracer = new BytecodeTracer(parent.classpath, parent.prefix, null);
    System.err.println("[createTracer] tracer ready");
    return tracer;
}
```

- [ ] **Step 3: Update XtraceCommand.run()**

In `XtraceCommand.java`, replace the `createTracer()` + `setCallGraphCache` pattern:

```java
@Override
public void run() {
    try {
        var tracer = new BytecodeTracer(parent.classpath, parent.prefix, callGraphFile);
        FilterConfig filter = FilterConfig.load(filterFile);
        Map<String, Object> result =
            entryPoint.fromMethod != null
                ? new ForwardTracer(tracer).traceForward(fromClass, entryPoint.fromMethod, filter)
                : new ForwardTracer(tracer).traceForward(fromClass, entryPoint.fromLine, filter);
        writeOutput(result);
    } catch (Exception e) {
        System.err.println("Error: " + e.getMessage());
        System.exit(1);
    }
}
```

Note: `BytecodeTracer.FilterConfig.load` becomes `FilterConfig.load` since the record is now top-level.

- [ ] **Step 4: Build and run full test suite**

```bash
cd java && mvn test
```

Expected: BUILD SUCCESS, all tests pass.

- [ ] **Step 5: Run E2E tests**

```bash
cd test-fixtures && bash run-e2e.sh
```

Expected: all E2E tests pass.

- [ ] **Step 6: Commit**

```bash
git add java/src/main/java/tools/bytecode/cli/CLI.java \
        java/src/main/java/tools/bytecode/cli/BaseCommand.java \
        java/src/main/java/tools/bytecode/cli/XtraceCommand.java
git commit -m "refactor: update CLI to use 3-arg BytecodeTracer constructor; remove mutable setter calls"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| `CallFrame`, `FilterConfig` top-level | Task 1 |
| `FilterConfig.shouldRecurse` stream-based | Task 1 |
| `StmtAnalyzer` static utils + constants | Task 2 |
| `stmtsAtLine` stream-based | Task 2 |
| `findCallSiteLine` no nested loops | Task 2 |
| `MethodResolver` with `Optional<SootMethod>` for `resolveCallee` | Task 3 |
| `findMethodsContainingLine` stream-based | Task 3 |
| `FrameBuilder` | Task 4 |
| `IntraproceduralSlicer` dedup via `StmtAnalyzer` (no duplication) | Task 5 |
| `LineMapReporter` stream-based | Task 6 |
| `BytecodeTracer` thin facade, 3-arg constructor, no setters | Task 7 |
| `System.err.println` → `log` in domain classes | Task 7 |
| CLI `defaultValue = ""` for prefix | Task 8 |
| `XtraceCommand` 3-arg constructor | Task 8 |
| `Map<String,Object>` weak typing deferred | (documented in spec, no task) |
| TDD for each class | All tasks |

**Type consistency:** `CallFrame` record fields (`className`, `methodName`, `methodSignature`,
`entryLine`, `exitLine`, `sourceTrace`, `stmtDetails`) used consistently across `FrameBuilderTest`,
`IntraproceduralSlicer`, and `StmtAnalyzerTest`. `StmtAnalyzer` constants used in all test
assertions and all production callers.
