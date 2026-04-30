# Spoon CFG Comparison Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a JUnit test that builds CFGs for `OrderService.processOrder` using both SootUp and Spoon, prints a side-by-side node comparison to stdout, and writes two SVGs to `target/`.

**Architecture:** `spoon-control-flow` is built from source and installed to local Maven repo. `spoon-core:11.2.0` and `spoon-control-flow:0.0.2-SNAPSHOT` are added as test-scoped deps. The test uses the existing `BytecodeTracer` for SootUp, and `ControlFlowBuilder` + `GraphVisPrettyPrinter` (both from spoon-control-flow) for Spoon. The SootUp DOT is generated in the test; the Spoon DOT comes from `graph.toGraphVisText()`. Both are rendered to SVG via `dot -Tsvg` subprocess. No production code changes.

**Tech Stack:** JUnit 5, SootUp 2.0.0 (existing), Spoon 11.2.0 + spoon-control-flow 0.0.2-SNAPSHOT (new test-scope, built from source), Graphviz `dot` CLI.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `java/pom.xml` | Modify | Add `spoon-core:11.2.0` and `spoon-control-flow:0.0.2-SNAPSHOT` test-scoped deps |
| `java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java` | Create | Single `@Test`; SootUp CFG + Spoon CFG; side-by-side stdout; two SVGs |

---

### Task 1: Build and install `spoon-control-flow` from source

**Files:** none in this repo — clones to `/tmp/spoon-src`

- [ ] **Step 1: Clone the Spoon repo**

```bash
git clone --depth=1 https://gitlab.ow2.org/spoon/spoon.git /tmp/spoon-src
```

Expected: clones successfully. If `/tmp/spoon-src` already exists, skip this step.

- [ ] **Step 2: Build and install `spoon-control-flow` to local Maven repo**

```bash
cd /tmp/spoon-src/spoon-control-flow && mvn install -DskipTests -q
```

Expected: `BUILD SUCCESS`. Artifact installed at `~/.m2/repository/fr/inria/gforge/spoon/spoon-control-flow/0.0.2-SNAPSHOT/`.

Verify:
```bash
ls ~/.m2/repository/fr/inria/gforge/spoon/spoon-control-flow/0.0.2-SNAPSHOT/*.jar
```

---

### Task 2: Add Spoon dependencies to `pom.xml`

**Files:**
- Modify: `java/pom.xml`

- [ ] **Step 1: Add both Spoon test-scope deps**

In `java/pom.xml`, add after the `junit-jupiter` dependency block (before `</dependencies>`):

```xml
        <dependency>
            <groupId>fr.inria.gforge.spoon</groupId>
            <artifactId>spoon-core</artifactId>
            <version>11.2.0</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>fr.inria.gforge.spoon</groupId>
            <artifactId>spoon-control-flow</artifactId>
            <version>0.0.2-SNAPSHOT</version>
            <scope>test</scope>
        </dependency>
```

- [ ] **Step 2: Verify resolution**

```bash
cd java && mvn dependency:resolve -q
```

Expected: `BUILD SUCCESS`, no download errors.

- [ ] **Step 3: Commit**

```bash
cd java
git add pom.xml
git commit -m "test: add spoon-core and spoon-control-flow as test deps for CFG comparison"
```

---

### Task 3: Write the test skeleton

**Files:**
- Create: `java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java`

- [ ] **Step 1: Create the test file**

```java
package tools.bytecode;

import org.junit.jupiter.api.Test;

class SpoonCfgComparisonTest {

  private static final String CLASSPATH = "../test-fixtures/classes";
  private static final String SOURCE_PATH = "../test-fixtures/src";
  private static final String CLASS_NAME = "com.example.app.OrderService";
  private static final String METHOD_NAME = "processOrder";

  @Test
  void compareCfgs() throws Exception {
    System.out.println("=== SootUp vs Spoon CFG comparison ===");
    System.out.println("TODO: implement");
  }
}
```

- [ ] **Step 2: Run to confirm it compiles and passes**

```bash
cd java && mvn test -Dtest=SpoonCfgComparisonTest -q
```

Expected: `BUILD SUCCESS`.

---

### Task 4: SootUp CFG extraction and stdout print

**Files:**
- Modify: `java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java`

- [ ] **Step 1: Replace the stub body with SootUp extraction**

Replace `compareCfgs` method body:

```java
  @Test
  void compareCfgs() throws Exception {
    // ----------------------------------------------------------------
    // SootUp side
    // ----------------------------------------------------------------
    BytecodeTracer tracer = new BytecodeTracer(CLASSPATH);
    sootup.core.model.SootMethod sootMethod =
        tracer.resolveMethodByName(CLASS_NAME, METHOD_NAME);
    sootup.core.graph.StmtGraph<?> stmtGraph = sootMethod.getBody().getStmtGraph();
    java.util.List<sootup.core.jimple.common.stmt.Stmt> sootNodes =
        new java.util.ArrayList<>(stmtGraph.getNodes());

    System.out.println("\n=== SOOTUP CFG NODES ===");
    for (int i = 0; i < sootNodes.size(); i++) {
      sootup.core.jimple.common.stmt.Stmt s = sootNodes.get(i);
      System.out.printf("  [n%d, line %3d] %s%n", i, BytecodeTracer.stmtLine(s), s);
    }

    System.out.println("\n=== SOOTUP CFG EDGES ===");
    for (int i = 0; i < sootNodes.size(); i++) {
      for (sootup.core.jimple.common.stmt.Stmt dst : stmtGraph.successors(sootNodes.get(i))) {
        System.out.printf("  n%d -> n%d%n", i, sootNodes.indexOf(dst));
      }
    }
  }
```

- [ ] **Step 2: Run and read SootUp output**

```bash
cd java && mvn test -Dtest=SpoonCfgComparisonTest 2>/dev/null
```

Expected: `BUILD SUCCESS`; SootUp Jimple statements with SSA variable names printed.

---

### Task 5: Spoon CFG extraction and stdout print

**Files:**
- Modify: `java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java`

- [ ] **Step 1: Add Spoon imports at the top of the file**

Add to the import block:

```java
import fr.inria.controlflow.ControlFlowBuilder;
import fr.inria.controlflow.ControlFlowGraph;
import fr.inria.controlflow.ControlFlowNode;
import fr.inria.controlflow.BranchKind;
import spoon.Launcher;
import spoon.reflect.code.CtVariableAccess;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.visitor.filter.TypeFilter;
```

- [ ] **Step 2: Add Spoon extraction inside `compareCfgs`, after the SootUp block**

```java
    // ----------------------------------------------------------------
    // Spoon side
    // ----------------------------------------------------------------
    Launcher launcher = new Launcher();
    launcher.addInputResource(SOURCE_PATH);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.buildModel();

    CtMethod<?> ctMethod = launcher.getFactory().Type()
        .get(CLASS_NAME)
        .getMethodsByName(METHOD_NAME)
        .get(0);

    ControlFlowBuilder builder = new ControlFlowBuilder();
    builder.build(ctMethod);
    ControlFlowGraph spoonGraph = builder.getResult();
    spoonGraph.simplifyConvergenceNodes();

    System.out.println("\n=== SPOON CFG NODES ===");
    for (ControlFlowNode n : spoonGraph.vertexSet()) {
      if (n.getStatement() == null) {
        System.out.printf("  [kind=%-12s] (no statement — %s)%n", n.getKind(), n.getKind());
        continue;
      }
      int line = n.getStatement().getPosition().isValidPosition()
          ? n.getStatement().getPosition().getLine() : -1;
      int col = n.getStatement().getPosition().isValidPosition()
          ? n.getStatement().getPosition().getColumn() : -1;
      java.util.List<String> vars = n.getStatement()
          .getElements(new TypeFilter<>(CtVariableAccess.class))
          .stream()
          .map(va -> va.getVariable().getSimpleName()
              + " (" + va.getType().getSimpleName() + ")")
          .distinct()
          .toList();
      System.out.printf("  [kind=%-12s, line %3d, col %2d] %s%n    vars: %s%n",
          n.getKind(), line, col, n.getStatement(), vars);
    }

    System.out.println("\n=== SPOON CFG EDGES ===");
    for (fr.inria.controlflow.ControlFlowEdge e : spoonGraph.edgeSet()) {
      System.out.printf("  %s -> %s%s%n",
          e.getSourceNode().getId(),
          e.getTargetNode().getId(),
          e.isBackEdge() ? " [back]" : "");
    }
```

- [ ] **Step 3: Run and read Spoon output**

```bash
cd java && mvn test -Dtest=SpoonCfgComparisonTest 2>/dev/null
```

Expected: `BUILD SUCCESS`; Spoon nodes show source-level text, original variable names, declared types, line+column.

---

### Task 6: Side-by-side comparison by line

**Files:**
- Modify: `java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java`

- [ ] **Step 1: Add comparison block after the Spoon extraction**

```java
    // ----------------------------------------------------------------
    // Side-by-side comparison matched by source line
    // ----------------------------------------------------------------
    java.util.Map<Integer, java.util.List<sootup.core.jimple.common.stmt.Stmt>> sootupByLine =
        sootNodes.stream()
            .collect(java.util.stream.Collectors.groupingBy(BytecodeTracer::stmtLine));

    java.util.Map<Integer, java.util.List<ControlFlowNode>> spoonByLine =
        spoonGraph.vertexSet().stream()
            .filter(n -> n.getStatement() != null
                && n.getStatement().getPosition().isValidPosition()
                && n.getKind() == BranchKind.STATEMENT || n.getKind() == BranchKind.BRANCH)
            .collect(java.util.stream.Collectors.groupingBy(
                n -> n.getStatement().getPosition().getLine()));

    java.util.Set<Integer> allLines = new java.util.TreeSet<>();
    allLines.addAll(sootupByLine.keySet());
    allLines.addAll(spoonByLine.keySet());

    System.out.println("\n=== SIDE-BY-SIDE COMPARISON (matched by source line) ===");
    for (int line : allLines) {
      if (line <= 0) continue;
      System.out.printf("%n--- Line %d ---%n", line);

      java.util.List<sootup.core.jimple.common.stmt.Stmt> su =
          sootupByLine.getOrDefault(line, java.util.List.of());
      java.util.List<ControlFlowNode> sp =
          spoonByLine.getOrDefault(line, java.util.List.of());

      if (su.isEmpty()) {
        System.out.println("  SOOTUP : (no match)");
      } else {
        su.forEach(s -> System.out.printf("  SOOTUP : %s%n", s));
      }

      if (sp.isEmpty()) {
        System.out.println("  SPOON  : (no match)");
      } else {
        sp.forEach(n -> {
          int col = n.getStatement().getPosition().getColumn();
          java.util.List<String> vars = n.getStatement()
              .getElements(new TypeFilter<>(CtVariableAccess.class))
              .stream()
              .map(va -> va.getVariable().getSimpleName()
                  + " (" + va.getType().getSimpleName() + ")")
              .distinct()
              .toList();
          System.out.printf("  SPOON  : %s  [col %d]%n           vars: %s%n",
              n.getStatement(), col, vars);
        });
      }
    }

    long matched = allLines.stream()
        .filter(l -> l > 0 && sootupByLine.containsKey(l) && spoonByLine.containsKey(l))
        .count();
    System.out.printf("%n=== SUMMARY: SootUp nodes=%d  Spoon nodes=%d  matched-by-line=%d ===%n",
        sootNodes.size(), spoonGraph.vertexSet().size(), matched);
```

- [ ] **Step 2: Run and verify**

```bash
cd java && mvn test -Dtest=SpoonCfgComparisonTest 2>/dev/null
```

Expected: `BUILD SUCCESS`; per-line comparison blocks and summary printed.

---

### Task 7: Generate DOT and SVG for both CFGs

**Files:**
- Modify: `java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java`

- [ ] **Step 1: Add DOT helper for SootUp and SVG writer to the class**

Add these private methods to the class:

```java
  private String sootupToDot(
      java.util.List<sootup.core.jimple.common.stmt.Stmt> nodes,
      sootup.core.graph.StmtGraph<?> g) {
    StringBuilder sb = new StringBuilder(
        "digraph sootup_cfg {\n  rankdir=TB;\n  node [shape=box fontname=monospace];\n");
    for (int i = 0; i < nodes.size(); i++) {
      sootup.core.jimple.common.stmt.Stmt s = nodes.get(i);
      String label = s.toString().replace("\"", "\\\"").replace("\n", "\\n");
      int line = BytecodeTracer.stmtLine(s);
      sb.append(String.format("  n%d [label=\"[L%d] %s\"];\n", i, line, label));
    }
    for (int i = 0; i < nodes.size(); i++) {
      for (sootup.core.jimple.common.stmt.Stmt dst : g.successors(nodes.get(i))) {
        int j = nodes.indexOf(dst);
        if (j >= 0) sb.append(String.format("  n%d -> n%d;\n", i, j));
      }
    }
    sb.append("}\n");
    return sb.toString();
  }

  private void writeDotAndSvg(String dot, String baseName) throws Exception {
    java.nio.file.Path targetDir = java.nio.file.Path.of("target");
    java.nio.file.Files.createDirectories(targetDir);
    java.nio.file.Path dotFile = targetDir.resolve(baseName + ".dot");
    java.nio.file.Path svgFile = targetDir.resolve(baseName + ".svg");
    java.nio.file.Files.writeString(dotFile, dot);
    Process p = new ProcessBuilder("dot", "-Tsvg", "-o", svgFile.toString(), dotFile.toString())
        .redirectErrorStream(true)
        .start();
    int exit = p.waitFor();
    String out = new String(p.getInputStream().readAllBytes());
    if (exit != 0) {
      System.err.println("[dot failed exit=" + exit + "]: " + out);
    } else {
      System.out.println("SVG written: " + svgFile.toAbsolutePath());
    }
  }
```

- [ ] **Step 2: Call both SVG generators at the end of `compareCfgs`**

Add at the end of `compareCfgs`, after the summary print:

```java
    // ----------------------------------------------------------------
    // Generate SVGs
    // ----------------------------------------------------------------
    writeDotAndSvg(sootupToDot(sootNodes, stmtGraph), "sootup-cfg");
    // Spoon: toGraphVisText() already returns valid DOT
    writeDotAndSvg(spoonGraph.toGraphVisText(), "spoon-cfg");
```

- [ ] **Step 3: Run and verify SVGs**

```bash
cd java && mvn test -Dtest=SpoonCfgComparisonTest 2>/dev/null
ls -la target/sootup-cfg.svg target/spoon-cfg.svg
open target/sootup-cfg.svg target/spoon-cfg.svg   # macOS
```

Expected: `BUILD SUCCESS`; two readable SVG files open in browser.

- [ ] **Step 4: Commit**

```bash
cd java
git add src/test/java/tools/bytecode/SpoonCfgComparisonTest.java
git commit -m "experiment: add Spoon vs SootUp CFG comparison test with SVG output"
```

---

## Self-Review

**Spec coverage:**
- [x] `spoon-core` + `spoon-control-flow` test dependencies — Tasks 1–2
- [x] SootUp CFG extraction using existing `BytecodeTracer` — Task 4
- [x] Spoon CFG via `ControlFlowBuilder` (proper library, not manual walk) — Task 5
- [x] Side-by-side stdout with variable names, types, positions — Task 6
- [x] `sootup-cfg.svg` and `spoon-cfg.svg` via `dot -Tsvg` — Task 7
- [x] No assertions; test always passes — enforced throughout

**Placeholder scan:** None found.

**Type consistency:**
- `BytecodeTracer.stmtLine` is package-visible (`static int stmtLine`) — test is in same package `tools.bytecode` ✓
- `sootupToDot` takes the `sootNodes` list and `stmtGraph` defined earlier in `compareCfgs` ✓
- `spoonGraph.toGraphVisText()` is the `ControlFlowGraph` instance built in Task 5 ✓
- `ControlFlowEdge` fully qualified where needed to avoid import conflicts ✓
