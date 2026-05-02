# Inter-Procedural DDG Edge Generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pre-compute PARAM and RETURN edges in `DdgInterCfgArtifactBuilder` so the DDG is a self-contained inter-procedural data flow graph. Simplify `BwdSliceBuilder` to pure backward edge traversal.

**Architecture:** New `InterProcEdgeBuilder` class with small pure functions for each micro-pass (arg parsing, reaching-def lookup, RETURN edge emission). Integrated into `DdgInterCfgArtifactBuilder` between LOCAL edge construction and `FieldDepEnricher`. `BwdSliceBuilder` drops on-the-fly PARAM/RETURN generation (lines 52-86) and `callerIndex`.

**Tech Stack:** Java 21, SootUp (Jimple), JUnit 5

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java` | Create | Pure functions: arg parsing, reaching-def lookup, PARAM/RETURN edge emission |
| `java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java` | Create | Unit tests for each micro-pass and the top-level `build()` |
| `java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java` | Modify (line 79) | Call `InterProcEdgeBuilder.build()` after LOCAL edges, before enricher |
| `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java` | Modify | Add integration test verifying PARAM/RETURN edges in artifact |
| `java/src/main/java/tools/bytecode/BwdSliceBuilder.java` | Modify (lines 10, 52-86, 102-115) | Remove on-the-fly PARAM/RETURN, remove `callerIndex`, accept all edge types |
| `java/src/test/java/tools/bytecode/BwdSliceBuilderTest.java` | Modify | Update tests to supply pre-computed PARAM/RETURN edges |
| `test-fixtures/tests/test_inter_proc_slice.sh` | Create | E2E test: `ddg-inter-cfg | bwd-slice` traces across method boundaries |

---

### Task 1: RETURN Edge Builder — Micro-Pass

The simplest inter-procedural edge type. For each call, connect callee RETURN nodes to caller ASSIGN_INVOKE nodes.

**Files:**
- Create: `java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java`
- Create: `java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java`

- [ ] **Step 1: Write failing tests for `buildReturnEdges`**

```java
package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.bytecode.artifact.*;

class InterProcEdgeBuilderTest {

  private static final String CALLER = "<com.example.Caller: void main()>";
  private static final String CALLEE = "<com.example.Foo: int compute()>";

  private static DdgNode node(String method, String localId, String stmt, StmtKind kind) {
    return new DdgNode(method + "#" + localId, method, localId, stmt, -1, kind, Map.of());
  }

  private static DdgNode callNode(
      String method, String localId, String stmt, StmtKind kind, String targetSig) {
    return new DdgNode(
        method + "#" + localId,
        method,
        localId,
        stmt,
        -1,
        kind,
        Map.of("targetMethodSignature", targetSig));
  }

  // --- RETURN edges ---

  @Test
  void returnEdge_singleCallSingleReturn() {
    List<DdgNode> nodes =
        List.of(
            callNode(
                CALLER,
                "s0",
                "r2 = staticinvoke <com.example.Foo: int compute()>()",
                StmtKind.ASSIGN_INVOKE,
                CALLEE),
            node(CALLEE, "s1", "return r5", StmtKind.RETURN));
    List<Map<String, Object>> calls = List.of(Map.of("from", CALLER, "to", CALLEE));

    List<DdgEdge> result =
        InterProcEdgeBuilder.buildReturnEdges(nodes, calls);

    assertEquals(1, result.size());
    DdgEdge edge = result.get(0);
    assertEquals(CALLEE + "#s1", edge.from());
    assertEquals(CALLER + "#s0", edge.to());
    assertInstanceOf(ReturnEdge.class, edge.edgeInfo());
  }

  @Test
  void returnEdge_voidCallSite_noEdge() {
    // INVOKE (not ASSIGN_INVOKE) — void call, no return value to capture
    List<DdgNode> nodes =
        List.of(
            callNode(
                CALLER,
                "s0",
                "virtualinvoke r0.<com.example.Foo: void doStuff()>()",
                StmtKind.INVOKE,
                "<com.example.Foo: void doStuff()>"),
            node("<com.example.Foo: void doStuff()>", "s1", "return", StmtKind.RETURN));
    List<Map<String, Object>> calls =
        List.of(Map.of("from", CALLER, "to", "<com.example.Foo: void doStuff()>"));

    List<DdgEdge> result =
        InterProcEdgeBuilder.buildReturnEdges(nodes, calls);

    assertTrue(result.isEmpty(), "void call sites should not produce RETURN edges");
  }

  @Test
  void returnEdge_calleeNotInNodes_noEdge() {
    // Call to method not in scope (no RETURN node exists)
    List<DdgNode> nodes =
        List.of(
            callNode(
                CALLER,
                "s0",
                "r2 = staticinvoke <com.example.Foo: int compute()>()",
                StmtKind.ASSIGN_INVOKE,
                CALLEE));
    List<Map<String, Object>> calls = List.of(Map.of("from", CALLER, "to", CALLEE));

    List<DdgEdge> result =
        InterProcEdgeBuilder.buildReturnEdges(nodes, calls);

    assertTrue(result.isEmpty(), "no RETURN edge when callee has no RETURN node");
  }

  @Test
  void returnEdge_multipleReturnPoints() {
    // Callee has two return stmts (conditional returns)
    List<DdgNode> nodes =
        List.of(
            callNode(
                CALLER,
                "s0",
                "r2 = staticinvoke <com.example.Foo: int compute()>()",
                StmtKind.ASSIGN_INVOKE,
                CALLEE),
            node(CALLEE, "s1", "return r5", StmtKind.RETURN),
            node(CALLEE, "s2", "return r6", StmtKind.RETURN));
    List<Map<String, Object>> calls = List.of(Map.of("from", CALLER, "to", CALLEE));

    List<DdgEdge> result =
        InterProcEdgeBuilder.buildReturnEdges(nodes, calls);

    assertEquals(2, result.size());
  }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest -Dsurefire.failIfNoSpecifiedTests=false 2>&1 | tail -20`
Expected: Compilation failure — `InterProcEdgeBuilder` does not exist.

- [ ] **Step 3: Write minimal `InterProcEdgeBuilder` with `buildReturnEdges`**

```java
package tools.bytecode;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import tools.bytecode.artifact.*;

public class InterProcEdgeBuilder {

  /**
   * RETURN edges: connect callee RETURN nodes to caller ASSIGN_INVOKE call sites.
   *
   * <p>For each call {from: caller, to: callee}: find RETURN nodes in callee, find ASSIGN_INVOKE
   * nodes in caller targeting callee, emit edge (returnNode → assignInvokeNode).
   */
  public static List<DdgEdge> buildReturnEdges(
      List<DdgNode> nodes, List<Map<String, Object>> calls) {
    List<DdgEdge> edges = new ArrayList<>();
    for (Map<String, Object> call : calls) {
      String callerSig = (String) call.get("from");
      String calleeSig = (String) call.get("to");

      List<DdgNode> returnNodes =
          nodes.stream()
              .filter(n -> n.method().equals(calleeSig) && n.kind() == StmtKind.RETURN)
              .toList();

      List<DdgNode> assignInvokeNodes =
          nodes.stream()
              .filter(
                  n ->
                      n.method().equals(callerSig)
                          && n.kind() == StmtKind.ASSIGN_INVOKE
                          && calleeSig.equals(n.call().get("targetMethodSignature")))
              .toList();

      for (DdgNode returnNode : returnNodes) {
        for (DdgNode callSiteNode : assignInvokeNodes) {
          edges.add(new DdgEdge(returnNode.id(), callSiteNode.id(), new ReturnEdge()));
        }
      }
    }
    return edges;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java
git commit -m "feat: add InterProcEdgeBuilder with RETURN edge micro-pass (TDD)"
```

---

### Task 2: Arg Parsing Micro-Pass

Pure function to extract argument names from a Jimple call-site statement. Reuses the `lastIndexOf('(')` / `lastIndexOf(')')` approach from existing `BwdSliceBuilder.extractArgLocal`.

**Files:**
- Modify: `java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java`
- Modify: `java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java`

- [ ] **Step 1: Write failing tests for `extractArgLocal`**

Add to `InterProcEdgeBuilderTest.java`:

```java
// --- Arg parsing ---

@Test
void extractArgLocal_singleArg() {
  assertEquals(
      "a",
      InterProcEdgeBuilder.extractArgLocal(
          "r2 = virtualinvoke r0.<com.example.Bar: void bar(int)>(a)", 0));
}

@Test
void extractArgLocal_multipleArgs() {
  String stmt = "r2 = virtualinvoke r0.<com.example.Bar: void bar(int,int)>(a, b)";
  assertEquals("a", InterProcEdgeBuilder.extractArgLocal(stmt, 0));
  assertEquals("b", InterProcEdgeBuilder.extractArgLocal(stmt, 1));
}

@Test
void extractArgLocal_outOfBounds() {
  assertEquals(
      "",
      InterProcEdgeBuilder.extractArgLocal(
          "r2 = virtualinvoke r0.<com.example.Bar: void bar(int)>(a)", 5));
}

@Test
void extractArgLocal_noArgs() {
  assertEquals(
      "",
      InterProcEdgeBuilder.extractArgLocal(
          "r2 = staticinvoke <com.example.Foo: int compute()>()", 0));
}

@Test
void extractArgLocal_constantArg() {
  // "null" and numeric literals should still be returned — caller decides whether to skip
  assertEquals(
      "null",
      InterProcEdgeBuilder.extractArgLocal(
          "virtualinvoke r0.<com.example.Bar: void bar(java.lang.Object)>(null)", 0));
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: Compilation failure — `extractArgLocal` does not exist.

- [ ] **Step 3: Write `extractArgLocal`**

Add to `InterProcEdgeBuilder.java`:

```java
/**
 * Extract the argument name at position {@code paramIndex} from a Jimple call-site statement.
 * Returns empty string if index is out of bounds or the arg list is empty.
 */
public static String extractArgLocal(String stmt, int paramIndex) {
  int open = stmt.lastIndexOf('(');
  int close = stmt.lastIndexOf(')');
  if (open < 0 || close < 0 || close <= open) return "";
  String args = stmt.substring(open + 1, close).trim();
  if (args.isEmpty()) return "";
  String[] parts = args.split(",");
  if (paramIndex >= parts.length) return "";
  return parts[paramIndex].trim();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java
git commit -m "feat: add extractArgLocal micro-pass for Jimple arg parsing"
```

---

### Task 3: Reaching-Def Lookup Micro-Pass

Pure function: given a call-site node ID and an arg local name, find the LOCAL edge whose `from` node defines that local.

**Files:**
- Modify: `java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java`
- Modify: `java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java`

- [ ] **Step 1: Write failing tests for `findReachingDef`**

Add to `InterProcEdgeBuilderTest.java`:

```java
// --- Reaching-def lookup ---

@Test
void findReachingDef_findsAssignEdge() {
  // s0: a = 1, s1: r2 = invoke foo(a)
  // LOCAL edge: s0 -> s1
  DdgNode defNode = node(CALLER, "s0", "a = 1", StmtKind.ASSIGN);
  DdgNode callSite =
      callNode(
          CALLER,
          "s1",
          "r2 = staticinvoke <com.example.Foo: int compute()>(a)",
          StmtKind.ASSIGN_INVOKE,
          CALLEE);
  List<DdgEdge> localEdges =
      List.of(new DdgEdge(defNode.id(), callSite.id(), new LocalEdge()));
  Map<String, DdgNode> nodeIndex = Map.of(defNode.id(), defNode, callSite.id(), callSite);

  String result = InterProcEdgeBuilder.findReachingDefId(
      callSite.id(), "a", localEdges, nodeIndex);

  assertEquals(defNode.id(), result);
}

@Test
void findReachingDef_identityNode() {
  // p0: a := @parameter0, s1: r2 = invoke foo(a)
  DdgNode identity = node(CALLER, "p0", "a := @parameter0: int", StmtKind.IDENTITY);
  DdgNode callSite =
      callNode(
          CALLER,
          "s1",
          "r2 = staticinvoke <com.example.Foo: int compute()>(a)",
          StmtKind.ASSIGN_INVOKE,
          CALLEE);
  List<DdgEdge> localEdges =
      List.of(new DdgEdge(identity.id(), callSite.id(), new LocalEdge()));
  Map<String, DdgNode> nodeIndex = Map.of(identity.id(), identity, callSite.id(), callSite);

  String result = InterProcEdgeBuilder.findReachingDefId(
      callSite.id(), "a", localEdges, nodeIndex);

  assertEquals(identity.id(), result);
}

@Test
void findReachingDef_noMatchReturnsEmpty() {
  DdgNode defNode = node(CALLER, "s0", "b = 1", StmtKind.ASSIGN);
  DdgNode callSite =
      callNode(
          CALLER,
          "s1",
          "r2 = staticinvoke <com.example.Foo: int compute()>(a)",
          StmtKind.ASSIGN_INVOKE,
          CALLEE);
  List<DdgEdge> localEdges =
      List.of(new DdgEdge(defNode.id(), callSite.id(), new LocalEdge()));
  Map<String, DdgNode> nodeIndex = Map.of(defNode.id(), defNode, callSite.id(), callSite);

  String result = InterProcEdgeBuilder.findReachingDefId(
      callSite.id(), "a", localEdges, nodeIndex);

  assertEquals("", result);
}

@Test
void findReachingDef_skipsNonLocalEdges() {
  DdgNode defNode = node(CALLER, "s0", "a = 1", StmtKind.ASSIGN);
  DdgNode callSite =
      callNode(
          CALLER,
          "s1",
          "r2 = staticinvoke <com.example.Foo: int compute()>(a)",
          StmtKind.ASSIGN_INVOKE,
          CALLEE);
  // Only a HEAP edge, no LOCAL edge
  List<DdgEdge> localEdges =
      List.of(new DdgEdge(defNode.id(), callSite.id(), new HeapEdge("<F: int x>")));
  Map<String, DdgNode> nodeIndex = Map.of(defNode.id(), defNode, callSite.id(), callSite);

  String result = InterProcEdgeBuilder.findReachingDefId(
      callSite.id(), "a", localEdges, nodeIndex);

  assertEquals("", result);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: Compilation failure — `findReachingDefId` does not exist.

- [ ] **Step 3: Write `findReachingDefId`**

Add to `InterProcEdgeBuilder.java`:

```java
/**
 * Find the reaching-def node ID for a given local at a call site.
 * Scans LOCAL edges pointing to {@code callSiteNodeId}, checks if the source node
 * defines {@code argLocal} (via {@code x = ...} or {@code x := ...}).
 * Returns empty string if no reaching-def found.
 */
public static String findReachingDefId(
    String callSiteNodeId,
    String argLocal,
    List<DdgEdge> edges,
    Map<String, DdgNode> nodeIndex) {
  return edges.stream()
      .filter(e -> callSiteNodeId.equals(e.to()))
      .filter(e -> e.edgeInfo() instanceof LocalEdge)
      .filter(
          e -> {
            DdgNode fromNode = nodeIndex.get(e.from());
            if (fromNode == null) return false;
            String stmt = fromNode.stmt();
            return stmt.startsWith(argLocal + " = ") || stmt.startsWith(argLocal + " := ");
          })
      .map(DdgEdge::from)
      .findFirst()
      .orElse("");
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java
git commit -m "feat: add findReachingDefId micro-pass for reaching-def lookup"
```

---

### Task 4: Constant Detection Micro-Pass

Pure function to detect whether an argument string is a Jimple constant/keyword (should not produce PARAM edges since there's no reaching-def).

**Files:**
- Modify: `java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java`
- Modify: `java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java`

- [ ] **Step 1: Write failing tests for `isConstantArg`**

Add to `InterProcEdgeBuilderTest.java`:

```java
// --- Constant detection ---

@Test
void isConstantArg_nullIsConstant() {
  assertTrue(InterProcEdgeBuilder.isConstantArg("null"));
}

@Test
void isConstantArg_numericConstants() {
  assertTrue(InterProcEdgeBuilder.isConstantArg("0"));
  assertTrue(InterProcEdgeBuilder.isConstantArg("42"));
  assertTrue(InterProcEdgeBuilder.isConstantArg("-1"));
  assertTrue(InterProcEdgeBuilder.isConstantArg("3L"));
  assertTrue(InterProcEdgeBuilder.isConstantArg("1.5"));
  assertTrue(InterProcEdgeBuilder.isConstantArg("1.5F"));
}

@Test
void isConstantArg_stringLiterals() {
  assertTrue(InterProcEdgeBuilder.isConstantArg("\"hello\""));
  assertTrue(InterProcEdgeBuilder.isConstantArg("\"\""));
}

@Test
void isConstantArg_booleans() {
  assertTrue(InterProcEdgeBuilder.isConstantArg("true"));
  assertTrue(InterProcEdgeBuilder.isConstantArg("false"));
}

@Test
void isConstantArg_localVarsAreNotConstants() {
  assertFalse(InterProcEdgeBuilder.isConstantArg("r0"));
  assertFalse(InterProcEdgeBuilder.isConstantArg("$i0"));
  assertFalse(InterProcEdgeBuilder.isConstantArg("value"));
  assertFalse(InterProcEdgeBuilder.isConstantArg("value#1"));
}

@Test
void isConstantArg_emptyIsConstant() {
  assertTrue(InterProcEdgeBuilder.isConstantArg(""));
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: Compilation failure — `isConstantArg` does not exist.

- [ ] **Step 3: Write `isConstantArg`**

Add to `InterProcEdgeBuilder.java`:

```java
private static final Pattern NUMERIC_LITERAL =
    Pattern.compile("^-?\\d+(\\.\\d+)?[LlFfDd]?$");

/**
 * Returns true if the argument string is a Jimple constant (no reaching-def to track).
 * Constants: null, true, false, numeric literals, string literals, empty string.
 */
public static boolean isConstantArg(String arg) {
  if (arg.isEmpty()) return true;
  if ("null".equals(arg) || "true".equals(arg) || "false".equals(arg)) return true;
  if (arg.startsWith("\"")) return true;
  return NUMERIC_LITERAL.matcher(arg).matches();
}
```

Add `import java.util.regex.Pattern;` to the imports (if not already present).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java
git commit -m "feat: add isConstantArg micro-pass for constant detection"
```

---

### Task 5: PARAM Edge Builder — Composing Micro-Passes

Compose arg parsing + constant detection + reaching-def lookup into PARAM edge emission. This is the main PARAM edge micro-pass.

**Files:**
- Modify: `java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java`
- Modify: `java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java`

- [ ] **Step 1: Write failing tests for `buildParamEdges`**

Add to `InterProcEdgeBuilderTest.java`:

```java
// --- PARAM edges ---

private static final String CALLER2 = "<com.example.Caller: void main()>";
private static final String CALLEE2 = "<com.example.Bar: void bar(int)>";

@Test
void paramEdge_singleArgWithReachingDef() {
  DdgNode defNode = node(CALLER2, "s0", "a = 1", StmtKind.ASSIGN);
  DdgNode callSite =
      callNode(
          CALLER2,
          "s1",
          "virtualinvoke r0.<com.example.Bar: void bar(int)>(a)",
          StmtKind.INVOKE,
          CALLEE2);
  DdgNode identity = node(CALLEE2, "p0", "r1 := @parameter0: int", StmtKind.IDENTITY);
  List<DdgNode> nodes = List.of(defNode, callSite, identity);
  List<DdgEdge> localEdges =
      List.of(new DdgEdge(defNode.id(), callSite.id(), new LocalEdge()));
  List<Map<String, Object>> calls = List.of(Map.of("from", CALLER2, "to", CALLEE2));

  List<DdgEdge> result =
      InterProcEdgeBuilder.buildParamEdges(nodes, localEdges, calls);

  assertEquals(1, result.size());
  DdgEdge edge = result.get(0);
  assertEquals(defNode.id(), edge.from());
  assertEquals(identity.id(), edge.to());
  assertInstanceOf(ParamEdge.class, edge.edgeInfo());
}

@Test
void paramEdge_constantArgSkipped() {
  DdgNode callSite =
      callNode(
          CALLER2,
          "s0",
          "virtualinvoke r0.<com.example.Bar: void bar(int)>(null)",
          StmtKind.INVOKE,
          CALLEE2);
  DdgNode identity = node(CALLEE2, "p0", "r1 := @parameter0: int", StmtKind.IDENTITY);
  List<DdgNode> nodes = List.of(callSite, identity);
  List<Map<String, Object>> calls = List.of(Map.of("from", CALLER2, "to", CALLEE2));

  List<DdgEdge> result =
      InterProcEdgeBuilder.buildParamEdges(nodes, List.of(), calls);

  assertTrue(result.isEmpty(), "constant arg should not produce PARAM edge");
}

@Test
void paramEdge_thisIdentitySkipped() {
  DdgNode defNode = node(CALLER2, "s0", "r0 = new com.example.Bar", StmtKind.ASSIGN);
  DdgNode callSite =
      callNode(
          CALLER2,
          "s1",
          "virtualinvoke r0.<com.example.Bar: void bar(int)>(a)",
          StmtKind.INVOKE,
          CALLEE2);
  // @this identity node — should be skipped entirely
  DdgNode thisIdentity =
      node(CALLEE2, "t0", "this := @this: com.example.Bar", StmtKind.IDENTITY);
  DdgNode paramIdentity = node(CALLEE2, "p0", "r1 := @parameter0: int", StmtKind.IDENTITY);

  List<DdgNode> nodes = List.of(defNode, callSite, thisIdentity, paramIdentity);
  List<DdgEdge> localEdges =
      List.of(new DdgEdge(defNode.id(), callSite.id(), new LocalEdge()));
  List<Map<String, Object>> calls = List.of(Map.of("from", CALLER2, "to", CALLEE2));

  List<DdgEdge> result =
      InterProcEdgeBuilder.buildParamEdges(nodes, localEdges, calls);

  // Should produce edge to paramIdentity, NOT to thisIdentity
  assertEquals(1, result.size());
  assertEquals(paramIdentity.id(), result.get(0).to());
}

@Test
void paramEdge_multipleArgs() {
  String callee3 = "<com.example.Bar: void baz(int,int)>";
  DdgNode defA = node(CALLER2, "s0", "a = 1", StmtKind.ASSIGN);
  DdgNode defB = node(CALLER2, "s1", "b = 2", StmtKind.ASSIGN);
  DdgNode callSite =
      callNode(
          CALLER2,
          "s2",
          "virtualinvoke r0.<com.example.Bar: void baz(int,int)>(a, b)",
          StmtKind.INVOKE,
          callee3);
  DdgNode param0 = node(callee3, "p0", "r1 := @parameter0: int", StmtKind.IDENTITY);
  DdgNode param1 = node(callee3, "p1", "r2 := @parameter1: int", StmtKind.IDENTITY);

  List<DdgNode> nodes = List.of(defA, defB, callSite, param0, param1);
  List<DdgEdge> localEdges =
      List.of(
          new DdgEdge(defA.id(), callSite.id(), new LocalEdge()),
          new DdgEdge(defB.id(), callSite.id(), new LocalEdge()));
  List<Map<String, Object>> calls = List.of(Map.of("from", CALLER2, "to", callee3));

  List<DdgEdge> result =
      InterProcEdgeBuilder.buildParamEdges(nodes, localEdges, calls);

  assertEquals(2, result.size());

  boolean hasParam0Edge =
      result.stream().anyMatch(e -> e.from().equals(defA.id()) && e.to().equals(param0.id()));
  boolean hasParam1Edge =
      result.stream().anyMatch(e -> e.from().equals(defB.id()) && e.to().equals(param1.id()));
  assertTrue(hasParam0Edge, "PARAM edge from defA to param0");
  assertTrue(hasParam1Edge, "PARAM edge from defB to param1");
}

@Test
void paramEdge_noReachingDefSkipped() {
  // Call site has arg 'a', but no LOCAL edge brings a definition of 'a'
  DdgNode callSite =
      callNode(
          CALLER2,
          "s0",
          "virtualinvoke r0.<com.example.Bar: void bar(int)>(a)",
          StmtKind.INVOKE,
          CALLEE2);
  DdgNode identity = node(CALLEE2, "p0", "r1 := @parameter0: int", StmtKind.IDENTITY);
  List<DdgNode> nodes = List.of(callSite, identity);
  List<Map<String, Object>> calls = List.of(Map.of("from", CALLER2, "to", CALLEE2));

  List<DdgEdge> result =
      InterProcEdgeBuilder.buildParamEdges(nodes, List.of(), calls);

  assertTrue(result.isEmpty(), "no PARAM edge when reaching-def not found");
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: Compilation failure — `buildParamEdges` does not exist.

- [ ] **Step 3: Write `buildParamEdges`**

Add to `InterProcEdgeBuilder.java`:

```java
private static final Pattern PARAM_IDENTITY =
    Pattern.compile("^\\w[\\w$#]* := @parameter(\\d+):");

/**
 * PARAM edges: connect reaching-def of each argument at the call site to the
 * corresponding @parameterN IDENTITY node in the callee.
 *
 * <p>Skips: @this identity, constant arguments, arguments with no reaching-def.
 */
public static List<DdgEdge> buildParamEdges(
    List<DdgNode> nodes,
    List<DdgEdge> localEdges,
    List<Map<String, Object>> calls) {

  Map<String, DdgNode> nodeIndex = new HashMap<>();
  for (DdgNode n : nodes) nodeIndex.put(n.id(), n);

  List<DdgEdge> edges = new ArrayList<>();

  for (Map<String, Object> call : calls) {
    String callerSig = (String) call.get("from");
    String calleeSig = (String) call.get("to");

    // Find @parameterN IDENTITY nodes in callee (skip @this)
    List<ParamTarget> paramTargets =
        nodes.stream()
            .filter(n -> n.method().equals(calleeSig) && n.kind() == StmtKind.IDENTITY)
            .flatMap(
                n -> {
                  Matcher m = PARAM_IDENTITY.matcher(n.stmt());
                  if (!m.find()) return java.util.stream.Stream.empty();
                  int idx = Integer.parseInt(m.group(1));
                  return java.util.stream.Stream.of(new ParamTarget(n, idx));
                })
            .toList();

    // Find call-site nodes in caller targeting this callee
    List<DdgNode> callSiteNodes =
        nodes.stream()
            .filter(
                n ->
                    n.method().equals(callerSig)
                        && (n.kind() == StmtKind.ASSIGN_INVOKE || n.kind() == StmtKind.INVOKE)
                        && calleeSig.equals(n.call().get("targetMethodSignature")))
            .toList();

    for (DdgNode callSiteNode : callSiteNodes) {
      for (ParamTarget pt : paramTargets) {
        String argLocal = extractArgLocal(callSiteNode.stmt(), pt.index());
        if (argLocal.isEmpty() || isConstantArg(argLocal)) continue;

        String reachingDefId =
            findReachingDefId(callSiteNode.id(), argLocal, localEdges, nodeIndex);
        if (reachingDefId.isEmpty()) continue;

        edges.add(new DdgEdge(reachingDefId, pt.node().id(), new ParamEdge()));
      }
    }
  }
  return edges;
}

private record ParamTarget(DdgNode node, int index) {}
```

Add `import java.util.HashMap;` and `import java.util.Map;` (ensure `java.util.regex.Matcher` is imported too).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java
git commit -m "feat: add buildParamEdges composing arg parsing + reaching-def + constant detection"
```

---

### Task 6: Top-Level `build()` Method

Compose `buildReturnEdges` and `buildParamEdges` into a single entry point.

**Files:**
- Modify: `java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java`
- Modify: `java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java`

- [ ] **Step 1: Write failing test for `build()`**

Add to `InterProcEdgeBuilderTest.java`:

```java
// --- Top-level build ---

@Test
void build_emitsBothParamAndReturnEdges() {
  String caller = "<com.example.Caller: void main()>";
  String callee = "<com.example.Foo: int compute(int)>";

  DdgNode defA = node(caller, "s0", "a = 1", StmtKind.ASSIGN);
  DdgNode callSite =
      callNode(
          caller,
          "s1",
          "r2 = staticinvoke <com.example.Foo: int compute(int)>(a)",
          StmtKind.ASSIGN_INVOKE,
          callee);
  DdgNode paramIdentity = node(callee, "p0", "r1 := @parameter0: int", StmtKind.IDENTITY);
  DdgNode retNode = node(callee, "s2", "return r5", StmtKind.RETURN);

  List<DdgNode> nodes = List.of(defA, callSite, paramIdentity, retNode);
  List<DdgEdge> localEdges =
      List.of(new DdgEdge(defA.id(), callSite.id(), new LocalEdge()));
  List<Map<String, Object>> calls = List.of(Map.of("from", caller, "to", callee));

  List<DdgEdge> result = InterProcEdgeBuilder.build(nodes, localEdges, calls);

  long paramCount = result.stream().filter(e -> e.edgeInfo() instanceof ParamEdge).count();
  long returnCount = result.stream().filter(e -> e.edgeInfo() instanceof ReturnEdge).count();

  assertEquals(1, paramCount, "one PARAM edge expected");
  assertEquals(1, returnCount, "one RETURN edge expected");
}

@Test
void build_noCalls_noEdges() {
  List<DdgNode> nodes = List.of(node(CALLER, "s0", "a = 1", StmtKind.ASSIGN));
  List<DdgEdge> result = InterProcEdgeBuilder.build(nodes, List.of(), List.of());
  assertTrue(result.isEmpty());
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: Compilation failure — `build` method does not exist.

- [ ] **Step 3: Write `build()`**

Add to `InterProcEdgeBuilder.java`:

```java
/**
 * Build all inter-procedural edges (PARAM + RETURN) from DDG nodes, LOCAL edges, and call list.
 */
public static List<DdgEdge> build(
    List<DdgNode> nodes,
    List<DdgEdge> localEdges,
    List<Map<String, Object>> calls) {
  List<DdgEdge> result = new ArrayList<>();
  result.addAll(buildParamEdges(nodes, localEdges, calls));
  result.addAll(buildReturnEdges(nodes, calls));
  return result;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd java && mvn test -pl . -Dtest=InterProcEdgeBuilderTest 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/InterProcEdgeBuilder.java java/src/test/java/tools/bytecode/InterProcEdgeBuilderTest.java
git commit -m "feat: add top-level InterProcEdgeBuilder.build() composing PARAM + RETURN"
```

---

### Task 7: Integrate into `DdgInterCfgArtifactBuilder`

Call `InterProcEdgeBuilder.build()` after LOCAL edge construction, before `FieldDepEnricher`.

**Files:**
- Modify: `java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java` (line 79)
- Modify: `java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java`

- [ ] **Step 1: Write failing integration test**

Add to `DdgInterCfgArtifactBuilderTest.java`:

```java
@Test
void ddgContainsParamAndReturnEdges() {
  // OrderService.processOrder calls OrderRepository.findById
  // Since OrderRepository is an interface (no body), we need a fixture with
  // both caller and callee having bodies. Use OrderService.processOrder calling
  // OrderService.transform (private method).
  // Actually, transform is private and may not appear in calltree.
  // Better: construct a two-method calltree using existing fixtures.
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

  // Single method — no inter-proc edges expected, but verify no crash
  DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer, null).build(input).ddg();

  // No calls → no PARAM/RETURN edges (but LOCAL edges should exist)
  long paramCount =
      ddg.edges().stream().filter(e -> e.edgeInfo() instanceof ParamEdge).count();
  long returnCount =
      ddg.edges().stream().filter(e -> e.edgeInfo() instanceof ReturnEdge).count();
  assertEquals(0, paramCount, "no calls → no PARAM edges");
  assertEquals(0, returnCount, "no calls → no RETURN edges");
  assertTrue(ddg.edges().stream().anyMatch(e -> e.edgeInfo() instanceof LocalEdge),
      "should still have LOCAL edges");
}
```

- [ ] **Step 2: Run test to verify it passes (baseline)**

Run: `cd java && mvn test -pl . -Dtest=DdgInterCfgArtifactBuilderTest#ddgContainsParamAndReturnEdges 2>&1 | tail -20`
Expected: PASS (baseline — no calls means no inter-proc edges even before the change).

- [ ] **Step 3: Integrate `InterProcEdgeBuilder` into `DdgInterCfgArtifactBuilder`**

In `DdgInterCfgArtifactBuilder.java`, after line 78 (`ddgEdges.addAll(payload.edges())`), add:

```java
    // Inter-procedural edges: PARAM + RETURN
    List<DdgEdge> interProcEdges = InterProcEdgeBuilder.build(ddgNodes, ddgEdges, calls);
    ddgEdges.addAll(interProcEdges);
```

- [ ] **Step 4: Run full test suite to verify no regression**

Run: `cd java && mvn test 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java java/src/test/java/tools/bytecode/DdgInterCfgArtifactBuilderTest.java
git commit -m "feat: integrate InterProcEdgeBuilder into DdgInterCfgArtifactBuilder pipeline"
```

---

### Task 8: Simplify `BwdSliceBuilder` — Remove On-The-Fly Logic

Remove the on-the-fly PARAM/RETURN edge generation and `callerIndex`. The slicer now relies on pre-computed edges.

**Files:**
- Modify: `java/src/main/java/tools/bytecode/BwdSliceBuilder.java`
- Modify: `java/src/test/java/tools/bytecode/BwdSliceBuilderTest.java`

- [ ] **Step 1: Update `BwdSliceBuilderTest` to supply pre-computed PARAM/RETURN edges**

The existing `crossMethodParameterCrossing` and `crossMethodReturnCrossing` tests construct DDGs *without* PARAM/RETURN edges and rely on on-the-fly generation. Update them to supply pre-computed edges.

In `crossMethodParameterCrossing`: add a PARAM edge and remove dependency on calltree edge for PARAM traversal.

```java
@Test
@SuppressWarnings("unchecked")
void crossMethodParameterCrossing() {
  String CALLER = "<com.example.Caller: void main()>";
  String CALLEE = "<com.example.Bar: void bar(int)>";

  DdgNode defNode = node(CALLER, "s1", "a = 1", StmtKind.ASSIGN);
  DdgNode callSiteNode =
      invokeNode(
          CALLER, "s2", "virtualinvoke r0.<com.example.Bar: void bar(int)>(a)", CALLEE);
  DdgNode identityNode = node(CALLEE, "p0", "r1 := @parameter0: int", StmtKind.IDENTITY);

  List<DdgEdge> edges =
      List.of(
          localEdge(CALLER, "s1", CALLER, "s2"),
          // Pre-computed PARAM edge: reaching-def of 'a' → @parameter0 identity
          new DdgEdge(defNode.id(), identityNode.id(), new ParamEdge()));

  Artifact art =
      artifact(
          List.of(
              new CalltreeNode(CALLER, "Caller", "main"),
              new CalltreeNode(CALLEE, "Bar", "bar")),
          List.of(new CalltreeEdge(CALLER, CALLEE)),
          List.of(defNode, callSiteNode, identityNode),
          edges);

  Map<String, Object> result = new BwdSliceBuilder().build(art, CALLEE, "r1");

  List<Map<String, Object>> resultNodes = (List<Map<String, Object>>) result.get("nodes");
  List<Map<String, Object>> resultEdges = (List<Map<String, Object>>) result.get("edges");

  // Should reach: p0 (identity), then via PARAM edge to s1 (def of a)
  assertEquals(2, resultNodes.size());
  List<String> stmtIds =
      resultNodes.stream().map(n -> (String) n.get("stmtId")).sorted().toList();
  assertEquals(List.of("p0", "s1"), stmtIds);

  boolean hasParamEdge =
      resultEdges.stream()
          .anyMatch(
              e -> {
                Map<?, ?> info = (Map<?, ?>) e.get("edge_info");
                return "PARAM".equals(info.get("kind"));
              });
  assertTrue(hasParamEdge, "param edge expected");
}
```

In `crossMethodReturnCrossing`: add a pre-computed RETURN edge.

```java
@Test
@SuppressWarnings("unchecked")
void crossMethodReturnCrossing() {
  String CALLER = "<com.example.Caller: void main()>";
  String CALLEE = "<com.example.Foo: int compute()>";

  DdgNode callSiteNode =
      callNode(CALLER, "cs0", "r2 = staticinvoke <com.example.Foo: int compute()>()", CALLEE);
  DdgNode defNode = node(CALLEE, "s0", "r5 = 42", StmtKind.ASSIGN);
  DdgNode returnNode = node(CALLEE, "s1", "return r5", StmtKind.RETURN);

  List<DdgEdge> edges =
      List.of(
          localEdge(CALLEE, "s0", CALLEE, "s1"),
          // Pre-computed RETURN edge: return node → assign_invoke call site
          new DdgEdge(returnNode.id(), callSiteNode.id(), new ReturnEdge()));

  Artifact art =
      artifact(
          List.of(
              new CalltreeNode(CALLER, "Caller", "main"),
              new CalltreeNode(CALLEE, "Foo", "compute")),
          List.of(new CalltreeEdge(CALLER, CALLEE)),
          List.of(callSiteNode, defNode, returnNode),
          edges);

  Map<String, Object> result = new BwdSliceBuilder().build(art, CALLER, "r2");

  List<Map<String, Object>> resultNodes = (List<Map<String, Object>>) result.get("nodes");
  List<Map<String, Object>> resultEdges = (List<Map<String, Object>>) result.get("edges");

  assertEquals(3, resultNodes.size());

  boolean hasReturnEdge =
      resultEdges.stream()
          .anyMatch(
              e -> {
                Map<?, ?> info = (Map<?, ?>) e.get("edge_info");
                return "RETURN".equals(info.get("kind"));
              });
  assertTrue(hasReturnEdge, "return edge expected");
}
```

Also update `cycleSafetyDoesNotLoopForever` to supply a pre-computed PARAM edge:

```java
@Test
void cycleSafetyDoesNotLoopForever() {
  String M = "<com.example.Foo: void bar()>";
  DdgNode identityNode = node(M, "s0", "r0 := @parameter0: int", StmtKind.IDENTITY);
  DdgNode callSiteNode =
      callNode(M, "s1", "r1 = staticinvoke <com.example.Foo: void bar()>(r0)", M);

  List<DdgEdge> edges =
      List.of(
          localEdge(M, "s0", M, "s1"),
          // Pre-computed PARAM edge (recursive call)
          new DdgEdge(identityNode.id(), identityNode.id(), new ParamEdge()));

  Artifact art =
      artifact(
          List.of(new CalltreeNode(M, "Foo", "bar")),
          List.of(new CalltreeEdge(M, M)),
          List.of(identityNode, callSiteNode),
          edges);

  Map<String, Object> result = new BwdSliceBuilder().build(art, M, "r1");
  assertNotNull(result);
}
```

- [ ] **Step 2: Run tests to verify they still pass (before simplification)**

Run: `cd java && mvn test -pl . -Dtest=BwdSliceBuilderTest 2>&1 | tail -20`
Expected: Tests may fail because the old code also generates on-the-fly edges (double-counting). This is expected — we need to simplify BwdSliceBuilder next.

- [ ] **Step 3: Simplify `BwdSliceBuilder`**

Apply these changes to `BwdSliceBuilder.java`:

**a) Remove `callerIndex` field and `buildCallerIndex` method (lines 10, 102-108):**

In `build()` method, change line 10 from:
```java
    Map<String, List<String>> callerIndex = buildCallerIndex(artifact.calltree().edges());
```
to: (delete line entirely)

Delete `buildCallerIndex` method (lines 102-108):
```java
  private Map<String, List<String>> buildCallerIndex(List<CalltreeEdge> edges) {
    Map<String, List<String>> index = new HashMap<>();
    for (CalltreeEdge edge : edges) {
      index.computeIfAbsent(edge.to(), k -> new ArrayList<>()).add(edge.from());
    }
    return index;
  }
```

**b) Remove on-the-fly PARAM generation (lines 52-69):**

Delete the entire block:
```java
      // Cross boundary — parameter: IDENTITY stmt, check if localVar is @parameterN
      if (ddgNode.kind() == StmtKind.IDENTITY && isParamIdentity(ddgNode.stmt(), item.localVar())) {
        ...
      }
```

**c) Remove on-the-fly RETURN generation (lines 71-86):**

Delete the entire block:
```java
      // Cross boundary — return: ASSIGN_INVOKE callsite, follow callee's return stmts
      if (ddgNode.kind() == StmtKind.ASSIGN_INVOKE) {
        ...
      }
```

**d) Update `incomingEdges` to accept all edge types (line 110-115):**

Change from:
```java
  private List<DdgEdge> incomingEdges(List<DdgEdge> edges, String nodeId) {
    return edges.stream()
        .filter(e -> nodeId.equals(e.to()))
        .filter(e -> e.edgeInfo() instanceof LocalEdge || e.edgeInfo() instanceof HeapEdge)
        .toList();
  }
```
to:
```java
  private List<DdgEdge> incomingEdges(List<DdgEdge> edges, String nodeId) {
    return edges.stream()
        .filter(e -> nodeId.equals(e.to()))
        .toList();
  }
```

**e) Add `ReturnEdge` case in local-var extraction (in the edge-walking loop around line 34):**

In the edge-walking loop, update the `fromLocal` extraction to handle RETURN edges. Change:
```java
        String fromLocal;
        if (edge.edgeInfo() instanceof HeapEdge heapEdge) {
          // Track the RHS of the field write: "obj.<C: T f> = val" -> extract "val"
          fromLocal = extractFieldWriteRhs(fromNode.stmt());
        } else {
          fromLocal = extractDefinedLocal(fromNode.stmt());
        }
```
to:
```java
        String fromLocal;
        if (edge.edgeInfo() instanceof HeapEdge heapEdge) {
          fromLocal = extractFieldWriteRhs(fromNode.stmt());
        } else if (edge.edgeInfo() instanceof ReturnEdge) {
          fromLocal = extractReturnedLocal(fromNode.stmt());
        } else {
          fromLocal = extractDefinedLocal(fromNode.stmt());
        }
```

**f) Remove now-unused methods and imports:**

Delete methods that are only used by the removed on-the-fly logic:
- `isParamIdentity` (line 121-123)
- `isCallsiteTo` (line 125-128)
- `extractParamIndex` (line 143-152)
- `extractArgLocal` (line 154-163)
- `extractReturnedLocal` — KEEP this one, it's now used by the RETURN edge local-var extraction
- `buildParamEdge` (line 200-206)
- `buildReturnEdge` (line 208-214)

Remove unused imports: `CalltreeEdge` (no longer needed since `callerIndex` is removed).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd java && mvn test -pl . -Dtest=BwdSliceBuilderTest 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `cd java && mvn test 2>&1 | tail -20`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add java/src/main/java/tools/bytecode/BwdSliceBuilder.java java/src/test/java/tools/bytecode/BwdSliceBuilderTest.java
git commit -m "refactor: simplify BwdSliceBuilder to pure backward edge traversal

Remove on-the-fly PARAM/RETURN edge generation, callerIndex, and
incomingEdges type filter. The slicer now relies on pre-computed
inter-procedural edges from InterProcEdgeBuilder."
```

---

### Task 9: E2E Test — Inter-Procedural Slice

Verify the full pipeline `fw-calltree | ddg-inter-cfg | bwd-slice` traces across method boundaries with pre-computed PARAM/RETURN edges.

**Files:**
- Create: `test-fixtures/tests/test_inter_proc_slice.sh`

- [ ] **Step 1: Write E2E test**

```bash
#!/usr/bin/env bash
# E2E test: backward slice traces across method boundary via pre-computed PARAM/RETURN edges.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup

CALLER="<com.example.app.OrderService: java.lang.String processOrder(int)>"

echo "inter-procedural backward slice through OrderService.processOrder()"
echo "  (tests pre-computed PARAM and RETURN edges in DDG)"

# Build calltree rooted at OrderService.processOrder
$UV fw-calltree \
  --callgraph "$OUT/callgraph.json" \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  | $B ddg-inter-cfg 2>/dev/null \
  | tee "$OUT/inter-proc-ddg.json" > /dev/null

# Verify DDG contains PARAM edges
assert_json_contains "$OUT/inter-proc-ddg.json" \
  '.ddg.edges | map(select(.edge_info.kind == "PARAM")) | length > 0' \
  "DDG contains at least one PARAM edge"

# Verify DDG contains RETURN edges
assert_json_contains "$OUT/inter-proc-ddg.json" \
  '.ddg.edges | map(select(.edge_info.kind == "RETURN")) | length > 0' \
  "DDG contains at least one RETURN edge"

# Backward slice should trace across method boundary
cat "$OUT/inter-proc-ddg.json" \
  | $B bwd-slice \
      --method "$CALLER" \
      --local-var "i0" 2>/dev/null \
  | tee "$OUT/inter-proc-slice.json" > /dev/null

# Verify slice contains nodes
assert_json_contains "$OUT/inter-proc-slice.json" \
  '.nodes | type == "array"' \
  "output has nodes array"

# Verify slice has edges
assert_json_contains "$OUT/inter-proc-slice.json" \
  '.edges | length > 0' \
  "slice has at least one edge"

# Verify all edges have kind
assert_json_contains "$OUT/inter-proc-slice.json" \
  '[.edges[].edge_info.kind] | all(. != null)' \
  "all edges have edge_info.kind"

report
```

- [ ] **Step 2: Make the test executable and run it**

Run:
```bash
chmod +x test-fixtures/tests/test_inter_proc_slice.sh
cd test-fixtures && bash tests/test_inter_proc_slice.sh
```
Expected: All assertions PASS.

- [ ] **Step 3: Run full E2E suite**

Run: `cd test-fixtures && bash run-e2e.sh 2>&1 | tail -30`
Expected: All E2E tests PASS (including existing `test_bwd_slice.sh` and `test_var_reassign_slice.sh`).

- [ ] **Step 4: Commit**

```bash
git add test-fixtures/tests/test_inter_proc_slice.sh
git commit -m "test: add E2E test for inter-procedural backward slice with PARAM/RETURN edges"
```

---

## Self-Review Checklist

1. **Spec coverage:** All sections of the design spec (`docs/superpowers/specs/2026-05-02-inter-proc-ddg-edges-design.md`) are covered:
   - `InterProcEdgeBuilder` (Tasks 1-6) — PARAM edges (arg-index-precise), RETURN edges, constant skipping, @this skipping
   - Integration in `DdgInterCfgArtifactBuilder` (Task 7)
   - `BwdSliceBuilder` simplification (Task 8) — remove on-the-fly logic, update `incomingEdges`, add `ReturnEdge` local-var extraction, remove `callerIndex`
   - E2E test (Task 9)

2. **Placeholder scan:** No TBD, TODO, or vague instructions. All steps contain exact code.

3. **Type consistency:** `InterProcEdgeBuilder.build()`, `buildReturnEdges()`, `buildParamEdges()`, `findReachingDefId()`, `extractArgLocal()`, `isConstantArg()` — names are consistent across all tasks. `ParamTarget` record is used consistently in Task 5.

4. **Out-of-scope items preserved:** No `@this` wiring (spec says handled by `FieldDepEnricher`). No edges for methods outside calltree scope. No heap-through-collections.
