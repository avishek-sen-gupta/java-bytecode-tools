# Fix Inter-Procedural DDG Edge Bugs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two bugs preventing PARAM/RETURN edges for interface-dispatched calls: SSA `#` in classifyStmt regex and signature mismatch in InterProcEdgeBuilder.

**Architecture:** Bug 2 (regex) is a one-character fix in `DdgInterCfgMethodGraphBuilder`. Bug 1 (signature mismatch) requires converting `InterProcEdgeBuilder` from static methods to instance methods, adding an `extractSubSignature` method, and wiring sub-signature matching into `buildReturnEdges` and `buildParamEdges`. Both bugs must be fixed for the integration test to pass.

**Tech Stack:** Java 21, JUnit 5, SootUp (Jimple bytecode analysis)

**Spec:** `docs/superpowers/specs/2026-05-02-inter-proc-edge-bugs-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java` | Modify line 54 | Fix `#` in classifyStmt regex |
| `java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java` | Modify | Convert static→instance, add `extractSubSignature`, wire sub-signature matching |
| `java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java` | Modify line 82 | Instantiate `InterProcEdgeBuilder`, call instance methods |
| `java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java` | Modify | Update all calls from static to instance, add sub-signature tests |
| `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java` | Modify | Add interface-dispatch integration test |
| `test-fixtures/tests/test_inter_proc_iface_dispatch.sh` | Create | E2E test for interface-dispatched inter-proc edges |

---

### Task 1: Fix classifyStmt regex (Bug 2)

**Files:**
- Modify: `java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java:54`
- Modify: `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java`

This is a one-character fix. The existing integration test fixtures (OrderService) use conditional branches, so SootUp may produce SSA-versioned locals. We verify via the integration test that call-site nodes are classified correctly.

- [ ] **Step 1: Write failing integration test**

Add to `DdgInterCfgArtifactBuilderTest.java` after the existing `ddgContainsParamAndReturnEdges` test:

```java
private static final String JDBC_FIND_BY_ID_SIG =
    "<com.example.app.JdbcOrderRepository: java.lang.String findById(int)>";

@Test
void classifiesAssignInvokeWithSsaVersionedLocal() {
  // OrderService.processOrder calls repo.findById(id) via interface dispatch.
  // SootUp may produce SSA-versioned locals (e.g., "order#1 = interfaceinvoke ...").
  // classifyStmt must classify these as ASSIGN_INVOKE, not INVOKE.
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

  // Find all call-site nodes that invoke findById
  var findByIdCallSites =
      ddg.nodes().stream()
          .filter(n -> n.method().equals(PROCESS_ORDER_SIG))
          .filter(n -> n.stmt().contains("findById"))
          .filter(n -> n.stmt().contains(" = "))
          .toList();

  assertFalse(findByIdCallSites.isEmpty(), "Should have at least one findById call site");

  for (DdgNode callSite : findByIdCallSites) {
    assertEquals(
        tools.bytecode.artifact.StmtKind.ASSIGN_INVOKE,
        callSite.kind(),
        "Call site should be ASSIGN_INVOKE, not INVOKE: " + callSite.stmt());
  }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd java && mvn test -pl . -Dtest="DdgInterCfgArtifactBuilderTest#classifiesAssignInvokeWithSsaVersionedLocal" -q`

Expected: FAIL — call sites with SSA-versioned locals (`order#1 = interfaceinvoke ...`) are classified as `INVOKE` instead of `ASSIGN_INVOKE`.

Note: If the test passes (SootUp happens to produce non-SSA locals for this method), the regex fix is still correct — proceed to Step 3 regardless. The fix prevents a bug for methods that do produce SSA locals.

- [ ] **Step 3: Fix the regex**

In `DdgInterCfgMethodGraphBuilder.java` line 54, change:

```java
    if ((text.startsWith("$") || text.matches("^\\w[\\w$]* = .+")) && text.contains("invoke "))
```

to:

```java
    if ((text.startsWith("$") || text.matches("^\\w[\\w$#]* = .+")) && text.contains("invoke "))
```

One character added: `#` inside the character class `[\\w$#]`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd java && mvn test -pl . -Dtest="DdgInterCfgArtifactBuilderTest" -q`
Expected: ALL tests PASS

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/DdgInterCfgMethodGraphBuilder.java \
        java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java
git commit -m "fix: add # to classifyStmt regex for SSA-versioned ASSIGN_INVOKE"
```

---

### Task 2: Convert InterProcEdgeBuilder from static to instance methods

**Files:**
- Modify: `java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java`
- Modify: `java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java:82`
- Modify: `java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java`

Convert all static methods to instance methods. No behavior change — pure refactor.

- [ ] **Step 1: Convert InterProcEdgeBuilder methods to instance**

In `InterProcEdgeBuilder.java`, remove `static` from all public methods:

```java
public class InterProcEdgeBuilder {

  private static final Pattern NUMERIC_LITERAL = Pattern.compile("^-?\\d+(\\.\\d+)?[LlFfDd]?$");
  private static final Pattern PARAM_IDENTITY =
      Pattern.compile("^\\w[\\w$#]* := @parameter(\\d+):");

  private record ParamTarget(DdgNode node, int index) {}

  public List<DdgEdge> build(
      List<DdgNode> nodes, List<DdgEdge> localEdges, List<Map<String, Object>> calls) {
    List<DdgEdge> result = new ArrayList<>();
    result.addAll(buildParamEdges(nodes, localEdges, calls));
    result.addAll(buildReturnEdges(nodes, calls));
    return result;
  }

  public List<DdgEdge> buildReturnEdges(
      List<DdgNode> nodes, List<Map<String, Object>> calls) {
    // ... same body, no changes ...
  }

  public String extractArgLocal(String stmt, int paramIndex) {
    // ... same body ...
  }

  public String findReachingDefId(
      String callSiteNodeId, String argLocal, List<DdgEdge> edges, Map<String, DdgNode> nodeIndex) {
    // ... same body ...
  }

  public boolean isConstantArg(String arg) {
    // ... same body ...
  }

  public List<DdgEdge> buildParamEdges(
      List<DdgNode> nodes, List<DdgEdge> localEdges, List<Map<String, Object>> calls) {
    // ... same body ...
  }
}
```

- [ ] **Step 2: Update DdgInterCfgArtifactBuilder to instantiate**

In `DdgInterCfgArtifactBuilder.java`, change line 82 from:

```java
    List<DdgEdge> interProcEdges = InterProcEdgeBuilder.build(ddgNodes, ddgEdges, calls);
```

to:

```java
    InterProcEdgeBuilder interProcBuilder = new InterProcEdgeBuilder();
    List<DdgEdge> interProcEdges = interProcBuilder.build(ddgNodes, ddgEdges, calls);
```

- [ ] **Step 3: Update all test calls from static to instance**

In `InterProcEdgeBuilderTest.java`:

1. Add a field at the top of the class:

```java
class InterProcEdgeBuilderTest {

  private final InterProcEdgeBuilder builder = new InterProcEdgeBuilder();
```

2. Replace every static call throughout the file. The pattern is:

| Before | After |
|--------|-------|
| `InterProcEdgeBuilder.buildReturnEdges(...)` | `builder.buildReturnEdges(...)` |
| `InterProcEdgeBuilder.extractArgLocal(...)` | `builder.extractArgLocal(...)` |
| `InterProcEdgeBuilder.findReachingDefId(...)` | `builder.findReachingDefId(...)` |
| `InterProcEdgeBuilder.isConstantArg(...)` | `builder.isConstantArg(...)` |
| `InterProcEdgeBuilder.buildParamEdges(...)` | `builder.buildParamEdges(...)` |
| `InterProcEdgeBuilder.build(...)` | `builder.build(...)` |

3. Remove `static` from the helper methods `node()` and `callNode()` (they reference no state but are in a class with instance fields now — keeping them static is fine too, either way works).

- [ ] **Step 4: Run all tests**

Run: `cd java && mvn test -pl . -q`
Expected: ALL tests PASS (no behavior change)

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java \
        java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java \
        java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java
git commit -m "refactor: convert InterProcEdgeBuilder from static to instance methods"
```

---

### Task 3: Add extractSubSignature and wire sub-signature matching (Bug 1)

**Files:**
- Modify: `java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java`
- Modify: `java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java`

Add an `extractSubSignature` instance method and update `buildReturnEdges` and `buildParamEdges` to use sub-signature matching instead of exact `equals()`.

- [ ] **Step 1: Write failing tests for extractSubSignature**

Add to `InterProcEdgeBuilderTest.java`:

```java
// --- Sub-signature extraction ---

@Test
void extractSubSignature_simpleMethod() {
  assertEquals(
      "findById(int)",
      builder.extractSubSignature(
          "<com.example.app.JdbcOrderRepository: java.lang.String findById(int)>"));
}

@Test
void extractSubSignature_multipleParams() {
  assertEquals(
      "bar(java.lang.String,int)",
      builder.extractSubSignature("<com.example.Foo: void bar(java.lang.String,int)>"));
}

@Test
void extractSubSignature_noParams() {
  assertEquals(
      "toString()",
      builder.extractSubSignature("<java.lang.Object: java.lang.String toString()>"));
}

@Test
void extractSubSignature_interfaceSignature() {
  assertEquals(
      "findById(int)",
      builder.extractSubSignature(
          "<com.example.app.OrderRepository: java.lang.String findById(int)>"));
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd java && mvn test -pl . -Dtest="InterProcEdgeBuilderTest#extractSubSignature*" -q`
Expected: FAIL — method does not exist

- [ ] **Step 3: Implement extractSubSignature**

Add to `InterProcEdgeBuilder.java`:

```java
/**
 * Extract the sub-signature (method name + parameter types) from a full Soot method signature.
 * E.g., from {@code <com.example.Foo: int bar(String,int)>} returns {@code bar(String,int)}.
 */
public String extractSubSignature(String methodSignature) {
  // Soot format: <ClassName: ReturnType methodName(ParamTypes)>
  // Find the method name: it starts after "ReturnType " and ends at ">"
  int parenOpen = methodSignature.indexOf('(');
  if (parenOpen < 0) return methodSignature;
  // Walk backwards from '(' to find the start of the method name (after the space)
  int nameStart = methodSignature.lastIndexOf(' ', parenOpen) + 1;
  int parenClose = methodSignature.lastIndexOf(')');
  if (parenClose < 0) return methodSignature;
  return methodSignature.substring(nameStart, parenClose + 1);
}
```

- [ ] **Step 4: Run extractSubSignature tests**

Run: `cd java && mvn test -pl . -Dtest="InterProcEdgeBuilderTest#extractSubSignature*" -q`
Expected: PASS

- [ ] **Step 5: Write failing tests for sub-signature matching in buildReturnEdges**

Add to `InterProcEdgeBuilderTest.java`:

```java
@Test
void returnEdge_interfaceDispatch_subSignatureMatch() {
  // Calltree resolves to concrete class, but Jimple call site uses interface signature
  String caller = "<com.example.Caller: void main()>";
  String concreteCallee = "<com.example.JdbcRepo: java.lang.String findById(int)>";
  String interfaceCallee = "<com.example.Repo: java.lang.String findById(int)>";

  DdgNode returnNode = node(concreteCallee, "return_0", "return r0", StmtKind.RETURN);
  // Call site targets the INTERFACE signature
  DdgNode assignInvokeNode =
      callNode(caller, "invoke_1", "$r0 = interfaceinvoke r1.<com.example.Repo: java.lang.String findById(int)>(i0)", StmtKind.ASSIGN_INVOKE, interfaceCallee);

  List<DdgNode> nodes = List.of(returnNode, assignInvokeNode);
  // Calltree edge uses CONCRETE signature
  List<Map<String, Object>> calls = List.of(Map.of("from", caller, "to", concreteCallee));

  List<DdgEdge> edges = builder.buildReturnEdges(nodes, calls);

  assertEquals(1, edges.size(), "Should produce RETURN edge via sub-signature match");
  assertEquals(returnNode.id(), edges.get(0).from());
  assertEquals(assignInvokeNode.id(), edges.get(0).to());
  assertInstanceOf(ReturnEdge.class, edges.get(0).edgeInfo());
}
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd java && mvn test -pl . -Dtest="InterProcEdgeBuilderTest#returnEdge_interfaceDispatch_subSignatureMatch" -q`
Expected: FAIL — 0 edges produced (exact match fails)

- [ ] **Step 7: Wire sub-signature matching into buildReturnEdges**

In `InterProcEdgeBuilder.java`, change `buildReturnEdges`. Replace the filter on line 68:

```java
                          && callee.equals(n.call().get("targetMethodSignature")))
```

with:

```java
                          && matchesSubSignature(callee, n.call().get("targetMethodSignature")))
```

Add the helper method:

```java
private boolean matchesSubSignature(String calltreeSig, String callSiteSig) {
  if (callSiteSig == null) return false;
  return extractSubSignature(calltreeSig).equals(extractSubSignature(callSiteSig));
}
```

- [ ] **Step 8: Run returnEdge tests**

Run: `cd java && mvn test -pl . -Dtest="InterProcEdgeBuilderTest#returnEdge*" -q`
Expected: ALL PASS (new test + existing tests)

- [ ] **Step 9: Write failing test for sub-signature matching in buildParamEdges**

Add to `InterProcEdgeBuilderTest.java`:

```java
@Test
void paramEdge_interfaceDispatch_subSignatureMatch() {
  String caller = "<com.example.Caller: void main()>";
  String concreteCallee = "<com.example.JdbcRepo: java.lang.String findById(int)>";
  String interfaceCallee = "<com.example.Repo: java.lang.String findById(int)>";

  DdgNode defNode = node(caller, "s0", "i0 = 42", StmtKind.ASSIGN);
  // Call site targets the INTERFACE signature
  DdgNode callSite =
      callNode(caller, "s1",
          "$r0 = interfaceinvoke r1.<com.example.Repo: java.lang.String findById(int)>(i0)",
          StmtKind.ASSIGN_INVOKE, interfaceCallee);
  DdgNode paramIdentity = node(concreteCallee, "p0", "r1 := @parameter0: int", StmtKind.IDENTITY);

  List<DdgNode> nodes = List.of(defNode, callSite, paramIdentity);
  List<DdgEdge> localEdges = List.of(new DdgEdge(defNode.id(), callSite.id(), new LocalEdge()));
  // Calltree edge uses CONCRETE signature
  List<Map<String, Object>> calls = List.of(Map.of("from", caller, "to", concreteCallee));

  List<DdgEdge> result = builder.buildParamEdges(nodes, localEdges, calls);

  assertEquals(1, result.size(), "Should produce PARAM edge via sub-signature match");
  assertEquals(defNode.id(), result.get(0).from());
  assertEquals(paramIdentity.id(), result.get(0).to());
  assertInstanceOf(ParamEdge.class, result.get(0).edgeInfo());
}
```

- [ ] **Step 10: Run test to verify it fails**

Run: `cd java && mvn test -pl . -Dtest="InterProcEdgeBuilderTest#paramEdge_interfaceDispatch_subSignatureMatch" -q`
Expected: FAIL — 0 edges produced

- [ ] **Step 11: Wire sub-signature matching into buildParamEdges**

In `InterProcEdgeBuilder.java`, change `buildParamEdges`. Replace the filter (currently at line ~172):

```java
                          && calleeSig.equals(n.call().get("targetMethodSignature")))
```

with:

```java
                          && matchesSubSignature(calleeSig, n.call().get("targetMethodSignature")))
```

- [ ] **Step 12: Run all InterProcEdgeBuilder tests**

Run: `cd java && mvn test -pl . -Dtest="InterProcEdgeBuilderTest" -q`
Expected: ALL PASS

- [ ] **Step 13: Commit**

```bash
git add java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java \
        java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java
git commit -m "fix: use sub-signature matching for inter-procedural edge generation

Interface-dispatched calls have different declaring class in Jimple
vs calltree. Match by method name + param types instead of full sig."
```

---

### Task 4: Integration test — interface-dispatched PARAM and RETURN edges

**Files:**
- Modify: `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java`

Verify that the full pipeline (DdgInterCfgArtifactBuilder → InterProcEdgeBuilder) generates PARAM and RETURN edges for `OrderService.processOrder` → `JdbcOrderRepository.findById`, where the call is through the `OrderRepository` interface.

- [ ] **Step 1: Write the integration test**

Add constant and test to `DdgInterCfgArtifactBuilderTest.java`:

```java
private static final String JDBC_FIND_BY_ID_SIG =
    "<com.example.app.JdbcOrderRepository: java.lang.String findById(int)>";

@Test
void interfaceDispatchGeneratesParamAndReturnEdges() {
  // OrderService.processOrder calls repo.findById(id) via OrderRepository interface.
  // Calltree resolves to JdbcOrderRepository (concrete).
  // Jimple call site will reference OrderRepository (interface).
  // Sub-signature matching should bridge the gap.
  Map<String, Object> input =
      Map.of(
          "nodes",
          Map.of(
              PROCESS_ORDER_SIG,
              Map.of(
                  "node_type", "java_method",
                  "class", "com.example.app.OrderService",
                  "method", "processOrder",
                  "methodSignature", PROCESS_ORDER_SIG),
              JDBC_FIND_BY_ID_SIG,
              Map.of(
                  "node_type", "java_method",
                  "class", "com.example.app.JdbcOrderRepository",
                  "method", "findById",
                  "methodSignature", JDBC_FIND_BY_ID_SIG)),
          "calls",
          List.of(Map.of("from", PROCESS_ORDER_SIG, "to", JDBC_FIND_BY_ID_SIG)),
          "metadata",
          Map.of("root", PROCESS_ORDER_SIG));

  DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer, null).build(input).ddg();

  long paramCount = ddg.edges().stream().filter(e -> e.edgeInfo() instanceof ParamEdge).count();
  long returnCount = ddg.edges().stream().filter(e -> e.edgeInfo() instanceof ReturnEdge).count();

  assertTrue(paramCount > 0,
      "Should have PARAM edges for interface-dispatched call. Nodes: "
          + ddg.nodes().stream()
              .filter(n -> n.stmt().contains("findById"))
              .map(n -> n.kind() + ": " + n.stmt())
              .toList());
  assertTrue(returnCount > 0,
      "Should have RETURN edges for interface-dispatched call");
}
```

- [ ] **Step 2: Run test**

Run: `cd java && mvn test -pl . -Dtest="DdgInterCfgArtifactBuilderTest#interfaceDispatchGeneratesParamAndReturnEdges" -q`
Expected: PASS (both bugs are fixed by Tasks 1 and 3)

- [ ] **Step 3: Run full test suite**

Run: `cd java && mvn test -pl . -q`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java
git commit -m "test: integration test for interface-dispatched PARAM/RETURN edges"
```

---

### Task 5: E2E test — backward slice through interface dispatch

**Files:**
- Create: `test-fixtures/tests/test_inter_proc_iface_dispatch.sh`

Verify the full pipeline: construct a calltree with `OrderService.processOrder` → `JdbcOrderRepository.findById` (concrete, as the calltree would provide), build DDG, run backward slice from `findById`'s parameter, verify the slice traces back through the PARAM edge.

- [ ] **Step 1: Write the E2E test**

Create `test-fixtures/tests/test_inter_proc_iface_dispatch.sh`:

```bash
#!/usr/bin/env bash
# E2E test: backward slice through interface-dispatched call.
# Verifies that PARAM/RETURN edges are generated when calltree uses concrete
# class signature but Jimple call site uses interface signature.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup

CALLER="<com.example.app.OrderService: java.lang.String processOrder(int)>"
CALLEE="<com.example.app.JdbcOrderRepository: java.lang.String findById(int)>"

echo "backward slice through interface-dispatched call"
echo "  OrderService.processOrder -> JdbcOrderRepository.findById"

cat > "$OUT/iface-dispatch-calltree.json" <<EOF
{
  "nodes": {
    "$CALLER": {
      "node_type": "java_method",
      "class": "com.example.app.OrderService",
      "method": "processOrder",
      "methodSignature": "$CALLER"
    },
    "$CALLEE": {
      "node_type": "java_method",
      "class": "com.example.app.JdbcOrderRepository",
      "method": "findById",
      "methodSignature": "$CALLEE"
    }
  },
  "calls": [
    {
      "from": "$CALLER",
      "to": "$CALLEE"
    }
  ],
  "metadata": {
    "root": "$CALLER"
  }
}
EOF

# Build DDG and verify inter-proc edges exist
cat "$OUT/iface-dispatch-calltree.json" \
  | $B ddg-inter-cfg 2>/dev/null \
  | tee "$OUT/iface-dispatch-ddg.json" > /dev/null

# Verify PARAM edges exist (interface dispatch bridged)
assert_json_contains "$OUT/iface-dispatch-ddg.json" \
  '[.ddg.edges[].edge_info.kind] | any(. == "PARAM")' \
  "DDG contains PARAM edges for interface-dispatched call"

# Verify RETURN edges exist
assert_json_contains "$OUT/iface-dispatch-ddg.json" \
  '[.ddg.edges[].edge_info.kind] | any(. == "RETURN")' \
  "DDG contains RETURN edges for interface-dispatched call"

# Backward slice from findById's parameter
cat "$OUT/iface-dispatch-calltree.json" \
  | $B ddg-inter-cfg 2>/dev/null \
  | $B bwd-slice \
      --method "$CALLEE" \
      --local-var "id" 2>/dev/null \
  | tee "$OUT/iface-dispatch-slice.json" > /dev/null

# Verify slice has nodes
assert_json_contains "$OUT/iface-dispatch-slice.json" \
  '.nodes | length > 0' \
  "slice has nodes"

# Verify slice has edges
assert_json_contains "$OUT/iface-dispatch-slice.json" \
  '.edges | length > 0' \
  "slice has edges"

# Verify slice contains PARAM edge (the inter-proc connection)
assert_json_contains "$OUT/iface-dispatch-slice.json" \
  '[.edges[].edge_info.kind] | any(. == "PARAM")' \
  "slice traces through PARAM edge across interface dispatch"

report
```

- [ ] **Step 2: Make executable**

```bash
chmod +x test-fixtures/tests/test_inter_proc_iface_dispatch.sh
```

- [ ] **Step 3: Run E2E test**

Run: `cd test-fixtures && bash tests/test_inter_proc_iface_dispatch.sh`
Expected: ALL assertions PASS

- [ ] **Step 4: Run full E2E suite**

Run: `cd test-fixtures && bash run-e2e.sh`
Expected: ALL tests PASS

- [ ] **Step 5: Commit**

```bash
git add test-fixtures/tests/test_inter_proc_iface_dispatch.sh
git commit -m "test: E2E test for backward slice through interface dispatch"
```
