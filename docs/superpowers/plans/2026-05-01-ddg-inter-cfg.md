# ddg-inter-cfg Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new Java CLI subcommand, `ddg-inter-cfg`, that reads a flat `fw-calltree` graph, resolves each reachable method with SootUp, and emits a compound JSON artifact containing preserved top-level `{nodes, calls}` plus per-method intraprocedural CFG/DDG payloads under `ddgs`.

**Architecture:** Keep the command thin. `DdgInterCfgCommand` owns Unix I/O and JSON parsing, `DdgInterCfgArtifactBuilder` owns top-level schema assembly and fail-fast validation, and `DdgInterCfgMethodGraphBuilder` owns statement-level graph extraction for one resolved `SootMethod`. Reuse the existing `BytecodeTracer` and SootUp DDG/CFG APIs instead of inventing new graph abstractions.

**Tech Stack:** Java 21, Jackson, Picocli, SootUp 2.0.0, JUnit 5, Maven, existing `test-fixtures` shell harness, Python `fw-calltree`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `java/src/main/java/tools/bytecode/cli/CLI.java` | Modify | Register `ddg-inter-cfg` and update help text |
| `java/src/main/java/tools/bytecode/cli/DdgInterCfgCommand.java` | Create | Read JSON from stdin or `--input`, invoke builder, write JSON to stdout or `--output` |
| `java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java` | Create | Validate top-level input shape, preserve `nodes`/`calls`, build `ddgs`, assemble metadata |
| `java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java` | Create | Build one method payload: statement nodes, CFG/DDG edges, helper ID lists |
| `java/src/test/java/tools/bytecode/cli/DdgInterCfgCommandParseTest.java` | Create | Picocli parsing and registration tests |
| `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java` | Create | Top-level schema, metadata, and fail-fast validation tests |
| `java/src/test/java/tools/bytecode/DdgInterCfgMethodGraphBuilderTest.java` | Create | Statement payload tests against `OrderService.processOrder` |
| `test-fixtures/tests/test_ddg_inter_cfg.sh` | Create | End-to-end stdin/stdout, `--input`/`--output`, and error-path coverage |

---

## Task 1: Add the CLI surface for `ddg-inter-cfg`

**Files:**
- Modify: `java/src/main/java/tools/bytecode/cli/CLI.java`
- Create: `java/src/main/java/tools/bytecode/cli/DdgInterCfgCommand.java`
- Create: `java/src/test/java/tools/bytecode/cli/DdgInterCfgCommandParseTest.java`

- [ ] **Step 1: Write failing Picocli tests**

Create `java/src/test/java/tools/bytecode/cli/DdgInterCfgCommandParseTest.java`:

```java
package tools.bytecode.cli;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import picocli.CommandLine;

class DdgInterCfgCommandParseTest {

  private static final String FAKE_CLASSPATH = "/tmp/fake";

  @Test
  void cliUsageListsDdgInterCfgSubcommand() {
    String usage = new CommandLine(new CLI()).getUsageMessage();
    assertTrue(usage.contains("ddg-inter-cfg"), usage);
  }

  @Test
  void acceptsNoInputOrOutputFlagsForPipeMode() {
    assertDoesNotThrow(
        () -> new CommandLine(new CLI()).parseArgs(FAKE_CLASSPATH, "ddg-inter-cfg"));
  }

  @Test
  void acceptsExplicitInputAndOutputFlags() {
    assertDoesNotThrow(
        () ->
            new CommandLine(new CLI())
                .parseArgs(
                    FAKE_CLASSPATH,
                    "ddg-inter-cfg",
                    "--input",
                    "/tmp/in.json",
                    "--output",
                    "/tmp/out.json"));
  }
}
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
cd java && mvn test -Dtest=DdgInterCfgCommandParseTest
```

Expected: failure because `ddg-inter-cfg` is not yet registered in `CLI`.

- [ ] **Step 3: Register the subcommand and add the command class**

Update `java/src/main/java/tools/bytecode/cli/CLI.java`:

```java
@Command(
    name = "bytecode",
    mixinStandardHelpOptions = true,
    description = {
      "SootUp-based interprocedural bytecode analysis.",
      "",
      "Usage: bytecode [--prefix <pkg.>] <classpath> <subcommand> [options]",
      "",
      "  --prefix  Limit analysis to classes whose FQCN starts with this string.",
      "            Without it, every class visible on the classpath is analyzed.",
      "  classpath Colon-separated compiled .class directories or jars.",
      "",
      "Subcommands: buildcg  dump  xtrace  ddg-inter-cfg",
      "",
      "JSON-producing commands write to stdout by default; use --output <file> to write a file.",
      "xtrace output can be piped into the Python post-processing tools:",
      "  ftrace-inter-slice | ftrace-intra-slice | ftrace-expand-refs | ftrace-semantic |"
          + " ftrace-to-dot",
      "  frames-print"
    },
    subcommands = {
      DumpCommand.class,
      BuildCgCommand.class,
      XtraceCommand.class,
      DdgInterCfgCommand.class
    })
public class CLI implements Runnable {
```

Create `java/src/main/java/tools/bytecode/cli/DdgInterCfgCommand.java`:

```java
package tools.bytecode.cli;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import tools.bytecode.DdgInterCfgArtifactBuilder;

@Command(
    name = "ddg-inter-cfg",
    mixinStandardHelpOptions = true,
    description = {
      "Read a flat fw-calltree graph and emit a compound {nodes, calls, ddgs, metadata} artifact.",
      "",
      "Input: stdin by default, or --input <file>",
      "Output: stdout by default, or --output <file>"
    })
class DdgInterCfgCommand extends BaseCommand {

  @Option(names = "--input", description = "Read fw-calltree JSON from file instead of stdin")
  Path input;

  @Override
  public void run() {
    try {
      InputStream in = input != null ? Files.newInputStream(input) : System.in;
      @SuppressWarnings("unchecked")
      Map<String, Object> calltree = mapper.readValue(in, Map.class);
      Map<String, Object> result =
          new DdgInterCfgArtifactBuilder(createTracer()).build(calltree);
      writeOutput(result);
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
}
```

- [ ] **Step 4: Re-run the parse tests**

Run:

```bash
cd java && mvn test -Dtest=DdgInterCfgCommandParseTest
```

Expected: BUILD SUCCESS, 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/cli/CLI.java \
        java/src/main/java/tools/bytecode/cli/DdgInterCfgCommand.java \
        java/src/test/java/tools/bytecode/cli/DdgInterCfgCommandParseTest.java
git commit -m "feat: add ddg-inter-cfg CLI entrypoint"
```

---

## Task 2: Build the per-method statement graph payload

**Files:**
- Create: `java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java`
- Create: `java/src/test/java/tools/bytecode/DdgInterCfgMethodGraphBuilderTest.java`

- [ ] **Step 1: Write the failing method-payload test**

Create `java/src/test/java/tools/bytecode/DdgInterCfgMethodGraphBuilderTest.java`:

```java
package tools.bytecode;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Paths;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import sootup.core.model.SootMethod;

class DdgInterCfgMethodGraphBuilderTest {

  private static BytecodeTracer tracer;
  private static SootMethod processOrder;

  @BeforeAll
  static void setUp() {
    String classpath = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    tracer = new BytecodeTracer(classpath, "com.example.app", null);
    processOrder = tracer.resolveMethodByName("com.example.app.OrderService", "processOrder");
  }

  @Test
  void buildsStatementNodesCfgEdgesDdgEdgesAndHelperLists() {
    Map<String, Object> payload = new DdgInterCfgMethodGraphBuilder().build(processOrder);

    @SuppressWarnings("unchecked")
    List<Map<String, Object>> nodes = (List<Map<String, Object>>) payload.get("nodes");
    @SuppressWarnings("unchecked")
    List<Map<String, Object>> edges = (List<Map<String, Object>>) payload.get("edges");
    @SuppressWarnings("unchecked")
    List<String> entryStmtIds = (List<String>) payload.get("entry_stmt_ids");
    @SuppressWarnings("unchecked")
    List<String> returnStmtIds = (List<String>) payload.get("return_stmt_ids");
    @SuppressWarnings("unchecked")
    List<String> callsiteStmtIds = (List<String>) payload.get("callsite_stmt_ids");

    assertFalse(nodes.isEmpty(), "Expected statement nodes");
    assertTrue(
        edges.stream().anyMatch(edge -> "cfg".equals(((Map<?, ?>) edge.get("edge_info")).get("kind"))),
        "Expected at least one cfg edge");
    assertTrue(
        edges.stream().anyMatch(edge -> "ddg".equals(((Map<?, ?>) edge.get("edge_info")).get("kind"))),
        "Expected at least one ddg edge");
    assertFalse(entryStmtIds.isEmpty(), "Expected entry statements");
    assertFalse(returnStmtIds.isEmpty(), "Expected return statements");
    assertFalse(callsiteStmtIds.isEmpty(), "Expected callsites");
  }
}
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
cd java && mvn test -Dtest=DdgInterCfgMethodGraphBuilderTest
```

Expected: compilation failure because `DdgInterCfgMethodGraphBuilder` does not exist.

- [ ] **Step 3: Implement the builder**

Create `java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java`:

```java
package tools.bytecode;

import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import sootup.codepropertygraph.ddg.DdgCreator;
import sootup.codepropertygraph.propertygraph.PropertyGraph;
import sootup.codepropertygraph.propertygraph.edges.DdgEdge;
import sootup.codepropertygraph.propertygraph.edges.PropertyGraphEdge;
import sootup.codepropertygraph.propertygraph.nodes.StmtGraphNode;
import sootup.core.jimple.common.stmt.AbstractInvokeExprStmt;
import sootup.core.jimple.common.stmt.JAssignStmt;
import sootup.core.jimple.common.stmt.JGotoStmt;
import sootup.core.jimple.common.stmt.JIdentityStmt;
import sootup.core.jimple.common.stmt.JIfStmt;
import sootup.core.jimple.common.stmt.JReturnStmt;
import sootup.core.jimple.common.stmt.JReturnVoidStmt;
import sootup.core.jimple.common.stmt.JSwitchStmt;
import sootup.core.jimple.common.stmt.JThrowStmt;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.SootMethod;

public class DdgInterCfgMethodGraphBuilder {

  public Map<String, Object> build(SootMethod method) {
    List<Stmt> stmts = new ArrayList<>(method.getBody().getStmtGraph().getStmts());
    Map<Stmt, String> stmtIds = new IdentityHashMap<>();
    List<Map<String, Object>> nodes = new ArrayList<>();
    List<Map<String, Object>> edges = new ArrayList<>();
    List<String> entryStmtIds = new ArrayList<>();
    List<String> returnStmtIds = new ArrayList<>();
    List<String> callsiteStmtIds = new ArrayList<>();

    for (int i = 0; i < stmts.size(); i++) {
      Stmt stmt = stmts.get(i);
      String stmtId = "s" + i;
      stmtIds.put(stmt, stmtId);
      nodes.add(toNode(stmtId, stmt));
      if (stmt instanceof JIdentityStmt) {
        entryStmtIds.add(stmtId);
      }
      if (stmt instanceof JReturnStmt || stmt instanceof JReturnVoidStmt) {
        returnStmtIds.add(stmtId);
      }
      if (isCallsite(stmt)) {
        callsiteStmtIds.add(stmtId);
      }
    }

    for (Stmt stmt : stmts) {
      String fromId = stmtIds.get(stmt);
      for (Stmt successor : method.getBody().getStmtGraph().successors(stmt)) {
        edges.add(cfgEdge(fromId, stmtIds.get(successor)));
      }
    }

    PropertyGraph ddg = new DdgCreator().createGraph(method);
    for (PropertyGraphEdge edge : ddg.getEdges()) {
      if (!(edge instanceof DdgEdge)) {
        continue;
      }
      if (!(edge.getSource() instanceof StmtGraphNode) || !(edge.getDestination() instanceof StmtGraphNode)) {
        continue;
      }
      Stmt fromStmt = ((StmtGraphNode) edge.getSource()).getStmt();
      Stmt toStmt = ((StmtGraphNode) edge.getDestination()).getStmt();
      if (stmtIds.containsKey(fromStmt) && stmtIds.containsKey(toStmt)) {
        edges.add(ddgEdge(stmtIds.get(fromStmt), stmtIds.get(toStmt), edge.getLabel()));
      }
    }

    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("nodes", nodes);
    payload.put("edges", edges);
    payload.put("entry_stmt_ids", entryStmtIds);
    payload.put("return_stmt_ids", returnStmtIds);
    payload.put("callsite_stmt_ids", callsiteStmtIds);
    return payload;
  }

  private static Map<String, Object> toNode(String stmtId, Stmt stmt) {
    Map<String, Object> node = new LinkedHashMap<>();
    node.put("id", stmtId);
    node.put("node_type", "stmt");
    node.put("stmt", stmt.toString());
    node.put("line", StmtAnalyzer.stmtLine(stmt));
    node.put("kind", stmtKind(stmt));
    if (stmt instanceof JIdentityStmt identity && identity.toString().contains("@this")) {
      node.put("isThis", true);
    }
    if (isCallsite(stmt)) {
      node.put("call", Map.of("targetMethodSignature", extractInvokeTarget(stmt)));
    }
    return node;
  }

  private static Map<String, Object> cfgEdge(String from, String to) {
    return Map.of("from", from, "to", to, "edge_info", Map.of("kind", "cfg"));
  }

  private static Map<String, Object> ddgEdge(String from, String to, String label) {
    Map<String, Object> edgeInfo = new LinkedHashMap<>();
    edgeInfo.put("kind", "ddg");
    edgeInfo.put("label", label);
    return Map.of("from", from, "to", to, "edge_info", edgeInfo);
  }

  private static boolean isCallsite(Stmt stmt) {
    if (stmt instanceof AbstractInvokeExprStmt) {
      return true;
    }
    return stmt instanceof JAssignStmt assign && assign.containsInvokeExpr();
  }

  private static String extractInvokeTarget(Stmt stmt) {
    if (stmt instanceof AbstractInvokeExprStmt invokeStmt) {
      return invokeStmt.getInvokeExpr().getMethodSignature().toString();
    }
    if (stmt instanceof JAssignStmt assign && assign.containsInvokeExpr()) {
      return assign.getInvokeExpr().getMethodSignature().toString();
    }
    return "";
  }

  private static String stmtKind(Stmt stmt) {
    if (stmt instanceof JIdentityStmt) return "identity";
    if (stmt instanceof JAssignStmt assign && assign.containsInvokeExpr()) return "assign_invoke";
    if (stmt instanceof AbstractInvokeExprStmt) return "invoke";
    if (stmt instanceof JAssignStmt) return "assign";
    if (stmt instanceof JIfStmt) return "if";
    if (stmt instanceof JReturnStmt) return "return";
    if (stmt instanceof JReturnVoidStmt) return "return_void";
    if (stmt instanceof JThrowStmt) return "throw";
    if (stmt instanceof JGotoStmt) return "goto";
    if (stmt instanceof JSwitchStmt) return "switch";
    return "other";
  }
}
```

- [ ] **Step 4: Re-run the method-payload test**

Run:

```bash
cd java && mvn test -Dtest=DdgInterCfgMethodGraphBuilderTest
```

Expected: BUILD SUCCESS, 1 test passes.

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java \
        java/src/test/java/tools/bytecode/DdgInterCfgMethodGraphBuilderTest.java
git commit -m "feat: build per-method cfg and ddg payloads"
```

---

## Task 3: Build the top-level artifact and fail-fast validation

**Files:**
- Create: `java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java`
- Create: `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java`

- [ ] **Step 1: Write failing artifact-builder tests**

Create `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java`:

```java
package tools.bytecode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class DdgInterCfgArtifactBuilderTest {

  private static final String PROCESS_ORDER_SIG =
      "<com.example.app.OrderService: java.lang.String processOrder(int)>";

  private static BytecodeTracer tracer;

  @BeforeAll
  static void setUp() {
    String classpath = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    tracer = new BytecodeTracer(classpath, "com.example.app", null);
  }

  @Test
  void preservesNodesAndCallsAndAddsDdgsAndMetadata() {
    Map<String, Object> input = new LinkedHashMap<>();
    input.put(
        "nodes",
        Map.of(
            PROCESS_ORDER_SIG,
            Map.of(
                "node_type", "java_method",
                "class", "com.example.app.OrderService",
                "method", "processOrder",
                "methodSignature", PROCESS_ORDER_SIG)));
    input.put("calls", List.of());
    input.put("metadata", Map.of("tool", "calltree"));

    Map<String, Object> output = new DdgInterCfgArtifactBuilder(tracer).build(input);

    assertEquals(input.get("nodes"), output.get("nodes"));
    assertEquals(input.get("calls"), output.get("calls"));
    assertTrue(((Map<?, ?>) output.get("ddgs")).containsKey(PROCESS_ORDER_SIG));
    assertEquals("ddg-inter-cfg", ((Map<?, ?>) output.get("metadata")).get("tool"));
    assertEquals("calltree", ((Map<?, ?>) output.get("metadata")).get("inputTool"));
    assertEquals(1, ((Map<?, ?>) output.get("metadata")).get("methodCount"));
    assertEquals(1, ((Map<?, ?>) output.get("metadata")).get("ddgCount"));
  }

  @Test
  void rejectsMissingNodes() {
    IllegalArgumentException ex =
        assertThrows(
            IllegalArgumentException.class,
            () -> new DdgInterCfgArtifactBuilder(tracer).build(Map.of("calls", List.of())));
    assertTrue(ex.getMessage().contains("nodes"), ex.getMessage());
  }
}
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
cd java && mvn test -Dtest=DdgInterCfgArtifactBuilderTest
```

Expected: compilation failure because `DdgInterCfgArtifactBuilder` does not exist.

- [ ] **Step 3: Implement the top-level builder**

Create `java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java`:

```java
package tools.bytecode;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import sootup.core.model.SootMethod;

public class DdgInterCfgArtifactBuilder {

  private final BytecodeTracer tracer;
  private final DdgInterCfgMethodGraphBuilder methodGraphBuilder = new DdgInterCfgMethodGraphBuilder();

  public DdgInterCfgArtifactBuilder(BytecodeTracer tracer) {
    this.tracer = tracer;
  }

  public Map<String, Object> build(Map<String, Object> input) {
    @SuppressWarnings("unchecked")
    Map<String, Object> nodes = (Map<String, Object>) input.get("nodes");
    if (nodes == null || nodes.isEmpty()) {
      throw new IllegalArgumentException("Input JSON must contain non-empty top-level 'nodes'");
    }

    @SuppressWarnings("unchecked")
    List<Map<String, Object>> calls =
        (List<Map<String, Object>>) input.getOrDefault("calls", List.of());

    Map<String, Object> ddgs = new LinkedHashMap<>();
    for (String methodSignature : nodes.keySet()) {
      SootMethod method = tracer.resolveMethod(methodSignature);
      if (!method.hasBody()) {
        throw new IllegalArgumentException("Resolved method has no body: " + methodSignature);
      }
      ddgs.put(methodSignature, methodGraphBuilder.build(method));
    }

    Map<String, Object> metadata = new LinkedHashMap<>();
    metadata.put("tool", "ddg-inter-cfg");
    Object inputMetadata = input.get("metadata");
    if (inputMetadata instanceof Map<?, ?> map && map.get("tool") != null) {
      metadata.put("inputTool", map.get("tool"));
    }
    metadata.put("methodCount", nodes.size());
    metadata.put("ddgCount", ddgs.size());

    Map<String, Object> output = new LinkedHashMap<>();
    output.put("nodes", nodes);
    output.put("calls", calls);
    output.put("ddgs", ddgs);
    output.put("metadata", metadata);
    return output;
  }
}
```

- [ ] **Step 4: Re-run the artifact-builder tests**

Run:

```bash
cd java && mvn test -Dtest=DdgInterCfgArtifactBuilderTest
```

Expected: BUILD SUCCESS, 2 tests pass.

- [ ] **Step 5: Run the focused Java test set together**

Run:

```bash
cd java && mvn test -Dtest=DdgInterCfgCommandParseTest,DdgInterCfgMethodGraphBuilderTest,DdgInterCfgArtifactBuilderTest
```

Expected: BUILD SUCCESS, all new focused tests pass together.

- [ ] **Step 6: Commit**

```bash
git add java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java \
        java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java
git commit -m "feat: assemble ddg inter cfg artifact"
```

---

## Task 4: Add end-to-end fixture coverage for Unix I/O and error behavior

**Files:**
- Create: `test-fixtures/tests/test_ddg_inter_cfg.sh`

- [ ] **Step 1: Write the end-to-end shell test**

Create `test-fixtures/tests/test_ddg_inter_cfg.sh`:

```bash
#!/usr/bin/env bash
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "ddg-inter-cfg stdin -> stdout"

$UV fw-calltree \
  --callgraph "$OUT/callgraph.json" \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  | $B ddg-inter-cfg 2>/dev/null | tee "$OUT/ddg-inter-cfg.json" > /dev/null

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.nodes | length > 0' \
  "top-level nodes preserved"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.calls | length >= 0' \
  "top-level calls preserved"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.metadata.tool == "ddg-inter-cfg"' \
  "metadata.tool is ddg-inter-cfg"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.ddgs | length > 0' \
  "ddgs map present"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.ddgs["<com.example.app.OrderService: java.lang.String processOrder(int)>"].nodes | length > 0' \
  "statement nodes present for processOrder"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '[.ddgs["<com.example.app.OrderService: java.lang.String processOrder(int)>"].edges[].edge_info.kind] | any(. == "cfg")' \
  "cfg edges present"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '[.ddgs["<com.example.app.OrderService: java.lang.String processOrder(int)>"].edges[].edge_info.kind] | any(. == "ddg")' \
  "ddg edges present"

echo ""
echo "ddg-inter-cfg --input/--output"

$UV fw-calltree \
  --callgraph "$OUT/callgraph.json" \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  > "$OUT/fw-calltree.json"

$B ddg-inter-cfg \
  --input "$OUT/fw-calltree.json" \
  --output "$OUT/ddg-inter-cfg-file.json" 2>/dev/null

assert_json_contains "$OUT/ddg-inter-cfg-file.json" \
  '.metadata.inputTool == "calltree"' \
  "inputTool copied from fw-calltree metadata"

echo ""
echo "ddg-inter-cfg invalid input"

printf '{\n  "calls": []\n}\n' > "$OUT/invalid-fw-calltree.json"

if $B ddg-inter-cfg --input "$OUT/invalid-fw-calltree.json" > "$OUT/invalid.log" 2>&1; then
  fail "invalid input exits non-zero" "command unexpectedly succeeded"
else
  pass "invalid input exits non-zero"
fi

assert_file_contains "$OUT/invalid.log" "nodes" "invalid input mentions missing nodes"

report
```

- [ ] **Step 2: Run the shell test and verify it fails first**

Run:

```bash
bash test-fixtures/tests/test_ddg_inter_cfg.sh
```

Expected: failure until the new command and builders are fully implemented.

- [ ] **Step 3: Run the shell test again after implementation**

Run:

```bash
bash test-fixtures/tests/test_ddg_inter_cfg.sh
```

Expected: all checks pass.

- [ ] **Step 4: Run the Java suite and the new fixture test together**

Run:

```bash
cd java && mvn test
cd .. && bash test-fixtures/tests/test_ddg_inter_cfg.sh
```

Expected: Maven test suite passes; new fixture test passes.

- [ ] **Step 5: Commit**

```bash
git add test-fixtures/tests/test_ddg_inter_cfg.sh
git commit -m "test: add ddg inter cfg end to end coverage"
```

---

## Final Verification

- [ ] Run the focused new tests:

```bash
cd java && mvn test -Dtest=DdgInterCfgCommandParseTest,DdgInterCfgMethodGraphBuilderTest,DdgInterCfgArtifactBuilderTest
```

- [ ] Run the full Java test suite:

```bash
cd java && mvn test
```

- [ ] Run the end-to-end fixture test:

```bash
cd .. && bash test-fixtures/tests/test_ddg_inter_cfg.sh
```

- [ ] Commit the remaining staged work:

```bash
git add java/src/main/java/tools/bytecode/cli/CLI.java \
        java/src/main/java/tools/bytecode/cli/DdgInterCfgCommand.java \
        java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java \
        java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java \
        java/src/test/java/tools/bytecode/cli/DdgInterCfgCommandParseTest.java \
        java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java \
        java/src/test/java/tools/bytecode/DdgInterCfgMethodGraphBuilderTest.java \
        test-fixtures/tests/test_ddg_inter_cfg.sh
git commit -m "feat: add ddg inter cfg artifact generator"
```

## Self-Review

- Spec coverage: the plan covers Unix I/O, preserved top-level `nodes`/`calls`, per-method `ddgs`, statement-node fields, CFG/DDG edge emission, helper ID lists, metadata, and fail-fast error handling. The spec’s out-of-scope items are intentionally absent.
- Placeholder scan: no `TODO`, `TBD`, or “handle appropriately” filler remains.
- Type consistency: every task uses the same top-level names from the spec: `nodes`, `calls`, `ddgs`, `metadata`, `entry_stmt_ids`, `return_stmt_ids`, and `callsite_stmt_ids`.
