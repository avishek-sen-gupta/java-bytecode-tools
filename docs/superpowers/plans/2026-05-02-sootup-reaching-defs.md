# Replace Hand-Rolled Reaching-Def and Stmt Classification with SootUp APIs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all regex-based string parsing in `DdgInterCfgMethodGraphBuilder` by using SootUp's `ReachingDefs` fixed-point analysis and structured `Stmt` type hierarchy.

**Architecture:** Replace the single-pass `buildDdgEdges()` with SootUp's `ReachingDefs` (fixed-point `ForwardFlowAnalysis`), which returns `Map<Stmt, List<Stmt>>` mapping each use-statement to its reaching def-statements. Replace `classifyStmt()` string matching with `instanceof` checks on SootUp's `JIdentityStmt`, `JReturnStmt`, `JAssignStmt`, `JInvokeStmt` types.

**Tech Stack:** Java 21, SootUp 2.0.0 (`sootup.analysis.intraprocedural.reachingdefs.ReachingDefs`), JUnit 5, bash E2E tests.

---

### Task 1: Red test — cross-block reaching-def edge

Write a test that fails with the current single-pass analysis: assert a LOCAL edge exists between a def and use that span non-adjacent basic blocks in `VarReassignService.sanitize()`.

**Files:**
- Modify: `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java`

- [ ] **Step 1: Write the failing test**

The current `buildDdgEdges` single-pass analysis cannot produce a LOCAL edge from the `value := @parameter0` identity node to the `return value` statement when they span non-adjacent basic blocks (the if-branch creates a split). Add this test:

```java
@Test
void crossBlockReachingDefProducesLocalEdge() {
    // VarReassignService.sanitize has an if-branch that splits the CFG.
    // The parameter identity "value := @parameter0" must reach "return value"
    // even though they are in different basic blocks.
    // The current single-pass analysis fails this because it walks blocks linearly
    // and loses the reaching-def across the branch merge point.
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                SANITIZE_SIG,
                Map.of(
                    "node_type", "java_method",
                    "class", "com.example.app.VarReassignService",
                    "method", "sanitize",
                    "methodSignature", SANITIZE_SIG)),
            "calls",
            List.of(),
            "metadata",
            Map.of("root", SANITIZE_SIG));

    DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer, null).build(input).ddg();

    // Find the IDENTITY node: "value := @parameter0: java.lang.String"
    DdgNode identityNode =
        ddg.nodes().stream()
            .filter(n -> n.method().equals(SANITIZE_SIG))
            .filter(n -> n.stmt().contains(":= @parameter0"))
            .findFirst()
            .orElseThrow(() -> new AssertionError("IDENTITY node for 'value' not found"));

    // Find the return node: "return value"
    DdgNode returnNode =
        ddg.nodes().stream()
            .filter(n -> n.method().equals(SANITIZE_SIG))
            .filter(n -> n.stmt().startsWith("return "))
            .findFirst()
            .orElseThrow(() -> new AssertionError("RETURN node not found"));

    // Assert: LOCAL edge from identity → return (cross-block reaching-def)
    boolean hasEdge =
        ddg.edges().stream()
            .filter(e -> e.edgeInfo() instanceof LocalEdge)
            .anyMatch(e -> e.from().equals(identityNode.id()) && e.to().equals(returnNode.id()));

    assertTrue(
        hasEdge,
        "Expected cross-block LOCAL edge from IDENTITY to RETURN: "
            + identityNode.id() + " -> " + returnNode.id()
            + "\nAll LOCAL edges: "
            + ddg.edges().stream()
                .filter(e -> e.edgeInfo() instanceof LocalEdge)
                .map(e -> e.from() + " -> " + e.to())
                .toList());
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/asgupta/code/java-bytecode-tools/java && mvn test -pl . -Dtest="DdgInterCfgArtifactBuilderTest#crossBlockReachingDefProducesLocalEdge" -q`

Expected: FAIL — the single-pass analysis doesn't produce this cross-block edge.

- [ ] **Step 3: Commit the red test**

```bash
cd /Users/asgupta/code/java-bytecode-tools/java
git add src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java
git commit -m "test: red test for cross-block reaching-def LOCAL edge

Asserts LOCAL edge from IDENTITY to RETURN in VarReassignService.sanitize,
which spans non-adjacent basic blocks. Fails with current single-pass analysis."
```

---

### Task 2: Replace `buildDdgEdges` with SootUp `ReachingDefs`

Replace the entire `buildDdgEdges` method, and delete all helper methods and regex patterns that were only used by it.

**Files:**
- Modify: `java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java`

- [ ] **Step 1: Replace `buildDdgEdges` and delete dead code**

In `DdgInterCfgMethodGraphBuilder.java`, make these changes:

1. Add imports at the top:

```java
import java.util.List;
import sootup.analysis.intraprocedural.reachingdefs.ReachingDefs;
import sootup.core.jimple.common.stmt.Stmt;
```

2. Delete these three regex pattern fields (lines 22-24):

```java
// DELETE:
private static final Pattern ASSIGN_LOCAL = Pattern.compile("^([#\\w][\\w$#]*) = (.+)$");
private static final Pattern IDENTITY_LOCAL = Pattern.compile("^([#\\w][\\w$#]*) := .+$");
private static final Pattern RETURN_VAL = Pattern.compile("^return ([#\\w][\\w$#]*)$");
```

3. Replace the `buildDdgEdges` method body (lines 66-96) with:

```java
private List<DdgEdge> buildDdgEdges(
    Body body, Map<Stmt, String> stmtToLocalId, String methodSig) {
  ReachingDefs rd = new ReachingDefs(body.getStmtGraph());
  Map<Stmt, List<Stmt>> defsByUse = rd.getReachingDefs();
  List<DdgEdge> edges = new ArrayList<>();
  for (var entry : defsByUse.entrySet()) {
    String toLocalId = stmtToLocalId.get(entry.getKey());
    if (toLocalId == null) continue;
    String toId = methodSig + "#" + toLocalId;
    for (Stmt defStmt : entry.getValue()) {
      String fromLocalId = stmtToLocalId.get(defStmt);
      if (fromLocalId == null) continue;
      String fromId = methodSig + "#" + fromLocalId;
      edges.add(new DdgEdge(fromId, toId, new LocalEdge()));
    }
  }
  return edges;
}
```

4. Delete these methods entirely — they are now dead code:
   - `extractUsedLocals` (lines 98-116)
   - `extractLocalsFromExpr` (lines 118-126)
   - `isJimpleKeyword` (lines 128-147)

5. Clean up unused imports: remove `import java.util.regex.Matcher;`, `import java.util.regex.Pattern;`, `import sootup.core.graph.BasicBlock;`.

- [ ] **Step 2: Run the red test to verify it passes**

Run: `cd /Users/asgupta/code/java-bytecode-tools/java && mvn test -pl . -Dtest="DdgInterCfgArtifactBuilderTest#crossBlockReachingDefProducesLocalEdge" -q`

Expected: PASS

- [ ] **Step 3: Run the full test suite to check for regressions**

Run: `cd /Users/asgupta/code/java-bytecode-tools/java && mvn test -q`

Expected: All tests pass. Some existing tests may need adjustment if they relied on the old analysis producing fewer edges — check test output carefully.

- [ ] **Step 4: Commit**

```bash
cd /Users/asgupta/code/java-bytecode-tools/java
git add src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java
git commit -m "feat: replace hand-rolled reaching-def with SootUp ReachingDefs

Replaces single-pass linear reaching-def walk with SootUp's fixed-point
ForwardFlowAnalysis. Fixes cross-block reaching-def failures in methods
with complex control flow (try-catch, branches).

Deletes ~80 lines of regex-based def/use extraction:
- ASSIGN_LOCAL, IDENTITY_LOCAL, RETURN_VAL patterns
- extractUsedLocals, extractLocalsFromExpr, isJimpleKeyword methods"
```

---

### Task 3: Replace `classifyStmt` regex with SootUp Stmt types

Replace string-based classification with `instanceof` checks on SootUp's structured type hierarchy.

**Files:**
- Modify: `java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java`

- [ ] **Step 1: Write a behavioral equivalence test**

In `DdgInterCfgArtifactBuilderTest.java`, add a test that verifies the new type-based classification produces the same `StmtKind` for every node as the current regex-based approach. This test uses the existing `processOrder` fixture which has IDENTITY, RETURN, ASSIGN_INVOKE, INVOKE, and ASSIGN statements.

```java
@Test
void classifyStmtMatchesForAllStmtKinds() {
    // Verify that all expected StmtKind values appear in processOrder's DDG nodes.
    // This ensures the Stmt-type-based classification covers the same cases
    // as the old regex-based approach.
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                PROCESS_ORDER_SIG,
                Map.of(
                    "node_type", "java_method",
                    "class", "com.example.app.OrderService",
                    "method", "processOrder",
                    "methodSignature", PROCESS_ORDER_SIG)),
            "calls",
            List.of(),
            "metadata",
            Map.of("root", PROCESS_ORDER_SIG));

    DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer, null).build(input).ddg();

    var kinds = ddg.nodes().stream()
        .map(DdgNode::kind)
        .collect(java.util.stream.Collectors.toSet());

    // processOrder has parameter identity, return, invoke (void calls),
    // assign-invoke (result-capturing calls), and plain assigns.
    assertTrue(kinds.contains(tools.bytecode.artifact.StmtKind.IDENTITY),
        "Expected IDENTITY nodes, got: " + kinds);
    assertTrue(kinds.contains(tools.bytecode.artifact.StmtKind.RETURN),
        "Expected RETURN nodes, got: " + kinds);
    assertTrue(kinds.contains(tools.bytecode.artifact.StmtKind.ASSIGN_INVOKE),
        "Expected ASSIGN_INVOKE nodes, got: " + kinds);
    assertTrue(kinds.contains(tools.bytecode.artifact.StmtKind.ASSIGN),
        "Expected ASSIGN nodes, got: " + kinds);
}
```

- [ ] **Step 2: Run test to verify it passes with current code**

Run: `cd /Users/asgupta/code/java-bytecode-tools/java && mvn test -pl . -Dtest="DdgInterCfgArtifactBuilderTest#classifyStmtMatchesForAllStmtKinds" -q`

Expected: PASS (this is a characterization test, not a red test).

- [ ] **Step 3: Replace `classifyStmt` implementation**

In `DdgInterCfgMethodGraphBuilder.java`, add imports:

```java
import sootup.core.jimple.common.stmt.JAssignStmt;
import sootup.core.jimple.common.stmt.JIdentityStmt;
import sootup.core.jimple.common.stmt.JInvokeStmt;
import sootup.core.jimple.common.stmt.JReturnStmt;
```

Replace the `classifyStmt` method (lines 50-58) with:

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

- [ ] **Step 4: Run the characterization test to verify equivalence**

Run: `cd /Users/asgupta/code/java-bytecode-tools/java && mvn test -pl . -Dtest="DdgInterCfgArtifactBuilderTest#classifyStmtMatchesForAllStmtKinds" -q`

Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/asgupta/code/java-bytecode-tools/java && mvn test -q`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
cd /Users/asgupta/code/java-bytecode-tools/java
git add src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java
git add src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java
git commit -m "refactor: replace classifyStmt regex with SootUp Stmt instanceof checks

Uses JIdentityStmt, JReturnStmt, JAssignStmt, JInvokeStmt type hierarchy
instead of string-matching on Jimple text. Adds characterization test
verifying all StmtKind values appear in processOrder fixture."
```

---

### Task 4: Run E2E tests and rebuild jar

Verify the full pipeline still works end-to-end.

**Files:**
- No file changes — verification only.

- [ ] **Step 1: Rebuild the jar**

Run: `cd /Users/asgupta/code/java-bytecode-tools/java && mvn package -q -DskipTests`

Expected: BUILD SUCCESS

- [ ] **Step 2: Run E2E test suite**

Run: `cd /Users/asgupta/code/java-bytecode-tools && bash test-fixtures/run-e2e.sh`

Expected: All E2E tests pass, including `test_ddg_inter_cfg.sh`, `test_bwd_slice.sh`, `test_var_reassign_slice.sh`, `test_inter_proc_iface_dispatch.sh`.

- [ ] **Step 3: If any E2E tests fail, diagnose and fix**

Read the failing test output. The most likely issue is tests that assert specific edge counts — `ReachingDefs` may produce more LOCAL edges than the old analysis, which is correct behavior. Update assertions if they are too tight.

---

### Task 5: Verify real-world pipeline reaches target allocation site

Re-run the backward slice pipeline against a real-world codebase to confirm the cross-block fix resolves the original bug.

**Files:**
- No file changes — verification only.

- [ ] **Step 1: Run the pipeline**

```bash
CP=~/code/<project>/target/classes
B="/Users/asgupta/code/java-bytecode-tools/scripts/bytecode.sh --prefix <pkg.prefix>. $CP"

uv --directory /Users/asgupta/code/java-bytecode-tools/python run fw-calltree \
  --callgraph ~/code/<project>/data/callgraph.json \
  --class <pkg.prefix>.web.EntryAction \
  --method entryMethod \
  --pattern '<pkg\.prefix>' \
  | $B ddg-inter-cfg 2>/dev/null \
  | $B bwd-slice \
      --method "<pkg.prefix.dao.DaoImpl: pkg.prefix.dao.ResultHandler buildQuery(java.util.Map)>" \
      --local-var "queryParams" 2>/dev/null \
  > /tmp/bwd-slice-queryParams-v3.json
```

- [ ] **Step 2: Verify the chain now reaches the Map creation**

```bash
jq '.nodes | length' /tmp/bwd-slice-queryParams-v3.json
jq '.nodes[] | {id: .id, stmt: .stmt, line: .line}' /tmp/bwd-slice-queryParams-v3.json
```

Expected: The chain should now include the `new HashMap` allocation node, connected via a cross-block LOCAL edge through the cast assignment.

- [ ] **Step 3: Report results**

Compare node count and chain depth with the v2 output (3 nodes, 2 PARAM edges). The v3 output should have more nodes showing the full dependency chain reaching the HashMap allocation.
