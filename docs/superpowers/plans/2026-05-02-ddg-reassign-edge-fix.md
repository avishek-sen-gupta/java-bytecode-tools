# DDG Variable Reassignment Edge Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `DdgInterCfgMethodGraphBuilder.buildDdgEdges()` so that when a variable is reassigned (e.g. `x = x.replace(...)`), the DDG correctly connects the prior definition to the reassigning statement instead of producing a bogus self-edge.

**Architecture:** The current two-pass algorithm builds a `localToDef` map in one pass (last-writer-wins), then uses that final map to build all edges in a second pass. For `x = x.replace(...)`, the second pass sees `localToDef["x"] = replace_stmt` and connects the replace stmt's use of `x` back to itself. The fix collapses to a single sequential pass: for each statement, first record edges from uses (using the currently-reaching definition), then update the reaching definition for the LHS. This is correct for straight-line code without branches.

**Tech Stack:** Java 21, SootUp, JUnit 5, Maven; bash + jq for E2E tests.

---

## File Structure

- **Modify:** `java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java` — fix `buildDdgEdges`
- **Modify:** `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java` — add integration test for the bug
- **Create:** `test-fixtures/src/com/example/app/VarReassignService.java` — fixture class with reassignment pattern
- **Create:** `test-fixtures/tests/test_var_reassign_slice.sh` — E2E test

---

## Background: The Bug

In `DdgInterCfgMethodGraphBuilder.buildDdgEdges()` (lines 64–86), the code:

1. **Pass 1** — iterates all stmts and builds `Map<String, Stmt> localToDef` keeping only the **last** definition of each local variable.
2. **Pass 2** — iterates all stmts again and for each used local, connects to `localToDef.get(local)`.

For `value = value.replace("*", "%")` (a reassignment where LHS == RHS variable):
- Pass 1 first stores `localToDef["value"] = line76_def`, then **overwrites** it with `localToDef["value"] = line215_replace`.
- Pass 2 processes line215's use of `value`: `localToDef.get("value")` returns `line215_replace` itself → self-edge.
- The correct edge `line76_def → line215_replace` is never emitted.

The fix: a single sequential pass — process each stmt in order, record use-edges using the current reaching definition, then update the definition.

---

## Task 1: Add fixture class and write the failing integration test

**Files:**
- Create: `test-fixtures/src/com/example/app/VarReassignService.java`
- Modify: `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java`

- [ ] **Step 1: Create the fixture class**

```java
// test-fixtures/src/com/example/app/VarReassignService.java
package com.example.app;

public class VarReassignService {
  public String sanitize(String value) {
    value = value.replace("*", "%");
    return value;
  }
}
```

This mirrors the real-world pattern: `value` is a parameter that is reassigned in-place via `replace()` then returned. In Jimple this produces:
- `value := @parameter0: java.lang.String`  (IDENTITY)
- `value = virtualinvoke value.<java.lang.String: java.lang.String replace(...)>(...)` (ASSIGN)
- `return value` (RETURN)

- [ ] **Step 2: Recompile the test fixtures**

The `lib-test.sh` setup only compiles when `classes/com/example/app` is absent. Force recompilation:

```bash
cd test-fixtures
rm -rf classes/com/example/app
javac -g -d classes src/com/example/app/*.java
```

Expected: no errors, `classes/com/example/app/VarReassignService.class` exists.

- [ ] **Step 3: Write the failing integration test**

Add this test to `DdgInterCfgArtifactBuilderTest`. Place it after the existing `rejectsEmptyNodes` test. Add the constant near the top of the class alongside existing constants:

```java
// Add near top of class alongside existing constants:
private static final String SANITIZE_SIG =
    "<com.example.app.VarReassignService: java.lang.String sanitize(java.lang.String)>";
```

```java
// Add this test method:
@Test
void ddgEdgeFromParamDefToReassignment() {
  // Reproduces the last-writer-wins bug in buildDdgEdges:
  // `value = value.replace(...)` must produce edge (identity_node → replace_node),
  // NOT a self-edge (replace_node → replace_node).
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
          "calls", List.of(),
          "metadata", Map.of("root", SANITIZE_SIG));

  DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer).build(input).ddg();

  // Find the IDENTITY node: "value := @parameter0: java.lang.String"
  var identityNode =
      ddg.nodes().stream()
          .filter(n -> n.method().equals(SANITIZE_SIG))
          .filter(n -> n.stmt().startsWith("value := @parameter0"))
          .findFirst()
          .orElseThrow(() -> new AssertionError("IDENTITY node for 'value' not found in DDG"));

  // Find the replace() reassignment node: "value = virtualinvoke value.<...replace...>(...)"
  var replaceNode =
      ddg.nodes().stream()
          .filter(n -> n.method().equals(SANITIZE_SIG))
          .filter(n -> n.stmt().startsWith("value = ") && n.stmt().contains("replace"))
          .findFirst()
          .orElseThrow(() -> new AssertionError("replace() reassignment node not found in DDG"));

  // Assert: edge from IDENTITY → replace (the correct reaching-def edge)
  boolean hasCorrectEdge =
      ddg.edges().stream()
          .anyMatch(
              e -> e.from().equals(identityNode.id()) && e.to().equals(replaceNode.id()));
  assertTrue(
      hasCorrectEdge,
      "Expected LOCAL edge from IDENTITY node to replace() node: "
          + identityNode.id() + " -> " + replaceNode.id()
          + "\nActual edges from identity: "
          + ddg.edges().stream()
              .filter(e -> e.from().equals(identityNode.id()))
              .map(e -> e.to())
              .toList());

  // Assert: no self-edge on replace node
  boolean hasSelfEdge =
      ddg.edges().stream()
          .anyMatch(e -> e.from().equals(replaceNode.id()) && e.to().equals(replaceNode.id()));
  assertFalse(
      hasSelfEdge,
      "Unexpected self-edge on replace() node: " + replaceNode.id());
}
```

- [ ] **Step 4: Run the test to confirm it fails**

```bash
cd java && mvn test -pl . -Dtest=DdgInterCfgArtifactBuilderTest#ddgEdgeFromParamDefToReassignment -q 2>&1 | tail -20
```

Expected: `AssertionError` — either "Expected LOCAL edge from IDENTITY node to replace() node" or "Unexpected self-edge on replace() node". This confirms the bug is real and the test is correctly detecting it.

- [ ] **Step 5: Commit the fixture and failing test**

```bash
git add test-fixtures/src/com/example/app/VarReassignService.java \
        test-fixtures/classes/com/example/app/VarReassignService.class \
        java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java
git commit -m "test: expose DDG self-edge bug for variable reassignment"
```

---

## Task 2: Fix `buildDdgEdges` to use a sequential single pass

**Files:**
- Modify: `java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java:64-86`

- [ ] **Step 1: Replace `buildDdgEdges` with the sequential single-pass implementation**

Replace the entire `buildDdgEdges` method (currently lines 64–86) with:

```java
private List<DdgEdge> buildDdgEdges(
    List<Stmt> stmts, Map<Stmt, String> stmtToLocalId, String methodSig) {
  Map<String, Stmt> reachingDef = new HashMap<>();
  List<DdgEdge> edges = new ArrayList<>();

  for (Stmt stmt : stmts) {
    String toId = methodSig + "#" + stmtToLocalId.get(stmt);

    // Step 1: record edges from uses, using the current reaching definition.
    // This must happen BEFORE updating reachingDef with this stmt's LHS,
    // so that `x = x.replace(...)` connects the prior def of x (not itself).
    for (String usedLocal : extractUsedLocals(stmt)) {
      Stmt defStmt = reachingDef.get(usedLocal);
      if (defStmt == null) continue;
      String fromId = methodSig + "#" + stmtToLocalId.get(defStmt);
      edges.add(new DdgEdge(fromId, toId, new LocalEdge()));
    }

    // Step 2: update reaching def for this stmt's LHS (after recording uses).
    String text = stmt.toString();
    Matcher assign = ASSIGN_LOCAL.matcher(text);
    Matcher identity = IDENTITY_LOCAL.matcher(text);
    if (assign.matches()) reachingDef.put(assign.group(1), stmt);
    else if (identity.matches()) reachingDef.put(identity.group(1), stmt);
  }

  return edges;
}
```

- [ ] **Step 2: Run the previously failing test — it must now pass**

```bash
cd java && mvn test -pl . -Dtest=DdgInterCfgArtifactBuilderTest#ddgEdgeFromParamDefToReassignment -q 2>&1 | tail -10
```

Expected: `BUILD SUCCESS`.

- [ ] **Step 3: Run the full unit test suite — all tests must pass**

```bash
cd java && mvn test -q 2>&1 | tail -10
```

Expected: `BUILD SUCCESS`, 0 failures. If any test fails, investigate before proceeding — do not continue.

- [ ] **Step 4: Commit the fix**

```bash
git add java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java
git commit -m "fix: DDG buildDdgEdges uses sequential pass to fix last-writer-wins self-edge bug"
```

---

## Task 3: Add E2E test for bwd-slice through variable reassignment

**Files:**
- Create: `test-fixtures/tests/test_var_reassign_slice.sh`

- [ ] **Step 1: Write the E2E test script**

```bash
#!/usr/bin/env bash
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

SANITIZE_METHOD="<com.example.app.VarReassignService: java.lang.String sanitize(java.lang.String)>"

echo "var reassign: bwd-slice follows def-use chain through variable reassignment"

$UV fw-calltree \
  --callgraph "$OUT/callgraph.json" \
  --class com.example.app.VarReassignService \
  --method sanitize \
  --pattern 'com\.example' \
  | $B ddg-inter-cfg 2>/dev/null \
  | tee "$OUT/var-reassign-ddg.json" > /dev/null

cat "$OUT/var-reassign-ddg.json" \
  | $B bwd-slice \
      --method "$SANITIZE_METHOD" \
      --local-var "value" 2>/dev/null \
  | tee "$OUT/var-reassign-slice.json" > /dev/null

assert_json_contains "$OUT/var-reassign-slice.json" \
  '.nodes | type == "array"' \
  "output has nodes array"

assert_json_contains "$OUT/var-reassign-slice.json" \
  '.edges | type == "array"' \
  "output has edges array"

assert_json_contains "$OUT/var-reassign-slice.json" \
  '.seed.method == "'"$SANITIZE_METHOD"'"' \
  "seed method is sanitize"

assert_json_contains "$OUT/var-reassign-slice.json" \
  '[.nodes[].stmt] | any(startswith("value := @parameter0"))' \
  "slice reaches parameter IDENTITY node (full chain through reassignment)"

assert_json_contains "$OUT/var-reassign-slice.json" \
  '[.nodes[].stmt] | any(startswith("value = ") and contains("replace"))' \
  "slice includes the replace() reassignment node"

report
```

- [ ] **Step 2: Make the script executable**

```bash
chmod +x test-fixtures/tests/test_var_reassign_slice.sh
```

- [ ] **Step 3: Run the E2E test alone to confirm it passes**

```bash
bash test-fixtures/tests/test_var_reassign_slice.sh
```

Expected: all assertions pass, `report` prints 0 failures.

- [ ] **Step 4: Run the full E2E suite to confirm no regressions**

```bash
bash test-fixtures/run-e2e.sh 2>&1 | tail -15
```

Expected: same pass count as before (all previous tests still pass) plus the new test passing.

- [ ] **Step 5: Commit the E2E test**

```bash
git add test-fixtures/tests/test_var_reassign_slice.sh
git commit -m "test(e2e): bwd-slice follows def-use chain through variable reassignment"
```
