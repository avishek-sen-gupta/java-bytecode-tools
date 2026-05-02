package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.bytecode.artifact.DdgEdge;
import tools.bytecode.artifact.DdgNode;
import tools.bytecode.artifact.HeapEdge;
import tools.bytecode.artifact.LocalEdge;
import tools.bytecode.artifact.ParamEdge;
import tools.bytecode.artifact.ReturnEdge;
import tools.bytecode.artifact.StmtKind;

class InterProcEdgeBuilderTest {

  private final InterProcEdgeBuilder builder = new InterProcEdgeBuilder();

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

  @Test
  void returnEdge_singleCallSingleReturn() {
    String caller = "<com.example.Foo: void bar()>";
    String callee = "<com.example.Baz: int qux()>";

    DdgNode returnNode = node(callee, "return_0", "return 42", StmtKind.RETURN);
    DdgNode assignInvokeNode =
        callNode(caller, "invoke_1", "$i0 = baz.qux()", StmtKind.ASSIGN_INVOKE, callee);

    List<DdgNode> nodes = List.of(returnNode, assignInvokeNode);
    List<Map<String, Object>> calls = List.of(Map.of("from", caller, "to", callee));

    List<DdgEdge> edges = builder.buildReturnEdges(nodes, calls);

    assertEquals(1, edges.size(), "Should produce 1 RETURN edge");
    DdgEdge edge = edges.get(0);
    assertEquals(returnNode.id(), edge.from(), "Edge should be from RETURN node");
    assertEquals(assignInvokeNode.id(), edge.to(), "Edge should be to ASSIGN_INVOKE node");
    assertInstanceOf(ReturnEdge.class, edge.edgeInfo(), "Edge should be a ReturnEdge");
  }

  @Test
  void returnEdge_voidCallSite_noEdge() {
    String caller = "<com.example.Foo: void bar()>";
    String callee = "<com.example.Baz: void qux()>";

    DdgNode returnNode = node(callee, "return_0", "return", StmtKind.RETURN);
    // INVOKE (not ASSIGN_INVOKE) for void call site
    DdgNode invokeNode = callNode(caller, "invoke_1", "baz.qux()", StmtKind.INVOKE, callee);

    List<DdgNode> nodes = List.of(returnNode, invokeNode);
    List<Map<String, Object>> calls = List.of(Map.of("from", caller, "to", callee));

    List<DdgEdge> edges = builder.buildReturnEdges(nodes, calls);

    assertEquals(0, edges.size(), "Should not produce RETURN edge for INVOKE (void) call site");
  }

  @Test
  void returnEdge_calleeNotInNodes_noEdge() {
    String caller = "<com.example.Foo: void bar()>";
    String callee = "<com.example.Baz: int qux()>";
    String missingCallee = "<com.example.Missing: int missing()>";

    DdgNode assignInvokeNode =
        callNode(caller, "invoke_1", "$i0 = foo.missing()", StmtKind.ASSIGN_INVOKE, missingCallee);

    List<DdgNode> nodes = List.of(assignInvokeNode);
    List<Map<String, Object>> calls = List.of(Map.of("from", caller, "to", callee));

    List<DdgEdge> edges = builder.buildReturnEdges(nodes, calls);

    assertEquals(0, edges.size(), "Should not produce RETURN edge when callee has no RETURN nodes");
  }

  @Test
  void returnEdge_multipleReturnPoints() {
    String caller = "<com.example.Foo: void bar()>";
    String callee = "<com.example.Baz: int qux(int)>";

    DdgNode returnNode1 = node(callee, "return_0", "return 42", StmtKind.RETURN);
    DdgNode returnNode2 = node(callee, "return_1", "return -1", StmtKind.RETURN);
    DdgNode assignInvokeNode =
        callNode(caller, "invoke_1", "$i0 = baz.qux(5)", StmtKind.ASSIGN_INVOKE, callee);

    List<DdgNode> nodes = List.of(returnNode1, returnNode2, assignInvokeNode);
    List<Map<String, Object>> calls = List.of(Map.of("from", caller, "to", callee));

    List<DdgEdge> edges = builder.buildReturnEdges(nodes, calls);

    assertEquals(2, edges.size(), "Should produce 2 RETURN edges for 2 return points");
    assertTrue(
        edges.stream()
            .allMatch(e -> e.from().equals(returnNode1.id()) || e.from().equals(returnNode2.id())),
        "All edges should be from RETURN nodes");
    assertTrue(
        edges.stream().allMatch(e -> e.to().equals(assignInvokeNode.id())),
        "All edges should be to the same ASSIGN_INVOKE node");
  }

  // --- Arg parsing ---

  @Test
  void extractArgLocal_singleArg() {
    assertEquals(
        "a",
        builder.extractArgLocal("r2 = virtualinvoke r0.<com.example.Bar: void bar(int)>(a)", 0));
  }

  @Test
  void extractArgLocal_multipleArgs() {
    String stmt = "r2 = virtualinvoke r0.<com.example.Bar: void bar(int,int)>(a, b)";
    assertEquals("a", builder.extractArgLocal(stmt, 0));
    assertEquals("b", builder.extractArgLocal(stmt, 1));
  }

  @Test
  void extractArgLocal_outOfBounds() {
    assertEquals(
        "",
        builder.extractArgLocal("r2 = virtualinvoke r0.<com.example.Bar: void bar(int)>(a)", 5));
  }

  @Test
  void extractArgLocal_noArgs() {
    assertEquals(
        "", builder.extractArgLocal("r2 = staticinvoke <com.example.Foo: int compute()>()", 0));
  }

  @Test
  void extractArgLocal_constantArg() {
    // "null" and numeric literals should still be returned — caller decides whether to skip
    assertEquals(
        "null",
        builder.extractArgLocal(
            "virtualinvoke r0.<com.example.Bar: void bar(java.lang.Object)>(null)", 0));
  }

  // --- Reaching-def lookup ---

  private static final String CALLER = "<com.example.Caller: void main()>";
  private static final String CALLEE = "<com.example.Foo: int compute()>";

  @Test
  void findReachingDef_findsAssignEdge() {
    DdgNode defNode = node(CALLER, "s0", "a = 1", StmtKind.ASSIGN);
    DdgNode callSite =
        callNode(
            CALLER,
            "s1",
            "r2 = staticinvoke <com.example.Foo: int compute()>(a)",
            StmtKind.ASSIGN_INVOKE,
            CALLEE);
    List<DdgEdge> localEdges = List.of(new DdgEdge(defNode.id(), callSite.id(), new LocalEdge()));
    Map<String, DdgNode> nodeIndex = Map.of(defNode.id(), defNode, callSite.id(), callSite);

    String result = builder.findReachingDefId(callSite.id(), "a", localEdges, nodeIndex);

    assertEquals(defNode.id(), result);
  }

  @Test
  void findReachingDef_identityNode() {
    DdgNode identity = node(CALLER, "p0", "a := @parameter0: int", StmtKind.IDENTITY);
    DdgNode callSite =
        callNode(
            CALLER,
            "s1",
            "r2 = staticinvoke <com.example.Foo: int compute()>(a)",
            StmtKind.ASSIGN_INVOKE,
            CALLEE);
    List<DdgEdge> localEdges = List.of(new DdgEdge(identity.id(), callSite.id(), new LocalEdge()));
    Map<String, DdgNode> nodeIndex = Map.of(identity.id(), identity, callSite.id(), callSite);

    String result = builder.findReachingDefId(callSite.id(), "a", localEdges, nodeIndex);

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
    List<DdgEdge> localEdges = List.of(new DdgEdge(defNode.id(), callSite.id(), new LocalEdge()));
    Map<String, DdgNode> nodeIndex = Map.of(defNode.id(), defNode, callSite.id(), callSite);

    String result = builder.findReachingDefId(callSite.id(), "a", localEdges, nodeIndex);

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
    List<DdgEdge> localEdges =
        List.of(new DdgEdge(defNode.id(), callSite.id(), new HeapEdge("<F: int x>")));
    Map<String, DdgNode> nodeIndex = Map.of(defNode.id(), defNode, callSite.id(), callSite);

    String result = builder.findReachingDefId(callSite.id(), "a", localEdges, nodeIndex);

    assertEquals("", result);
  }

  // --- Constant detection ---

  @Test
  void isConstantArg_nullIsConstant() {
    assertTrue(builder.isConstantArg("null"));
  }

  @Test
  void isConstantArg_numericConstants() {
    assertTrue(builder.isConstantArg("0"));
    assertTrue(builder.isConstantArg("42"));
    assertTrue(builder.isConstantArg("-1"));
    assertTrue(builder.isConstantArg("3L"));
    assertTrue(builder.isConstantArg("1.5"));
    assertTrue(builder.isConstantArg("1.5F"));
  }

  @Test
  void isConstantArg_stringLiterals() {
    assertTrue(builder.isConstantArg("\"hello\""));
    assertTrue(builder.isConstantArg("\"\""));
  }

  @Test
  void isConstantArg_booleans() {
    assertTrue(builder.isConstantArg("true"));
    assertTrue(builder.isConstantArg("false"));
  }

  @Test
  void isConstantArg_localVarsAreNotConstants() {
    assertFalse(builder.isConstantArg("r0"));
    assertFalse(builder.isConstantArg("$i0"));
    assertFalse(builder.isConstantArg("value"));
    assertFalse(builder.isConstantArg("value#1"));
  }

  @Test
  void isConstantArg_emptyIsConstant() {
    assertTrue(builder.isConstantArg(""));
  }

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
    List<DdgEdge> localEdges = List.of(new DdgEdge(defNode.id(), callSite.id(), new LocalEdge()));
    List<Map<String, Object>> calls = List.of(Map.of("from", CALLER2, "to", CALLEE2));

    List<DdgEdge> result = builder.buildParamEdges(nodes, localEdges, calls);

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

    List<DdgEdge> result = builder.buildParamEdges(nodes, List.of(), calls);

    assertTrue(result.isEmpty(), "constant arg should not produce PARAM edge");
  }

  @Test
  void paramEdge_thisIdentitySkipped() {
    DdgNode defA = node(CALLER2, "s0", "a = 1", StmtKind.ASSIGN);
    DdgNode callSite =
        callNode(
            CALLER2,
            "s1",
            "virtualinvoke r0.<com.example.Bar: void bar(int)>(a)",
            StmtKind.INVOKE,
            CALLEE2);
    // @this identity node — should be skipped entirely
    DdgNode thisIdentity = node(CALLEE2, "t0", "this := @this: com.example.Bar", StmtKind.IDENTITY);
    DdgNode paramIdentity = node(CALLEE2, "p0", "r1 := @parameter0: int", StmtKind.IDENTITY);

    List<DdgNode> nodes = List.of(defA, callSite, thisIdentity, paramIdentity);
    List<DdgEdge> localEdges = List.of(new DdgEdge(defA.id(), callSite.id(), new LocalEdge()));
    List<Map<String, Object>> calls = List.of(Map.of("from", CALLER2, "to", CALLEE2));

    List<DdgEdge> result = builder.buildParamEdges(nodes, localEdges, calls);

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

    List<DdgEdge> result = builder.buildParamEdges(nodes, localEdges, calls);

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

    List<DdgEdge> result = builder.buildParamEdges(nodes, List.of(), calls);

    assertTrue(result.isEmpty(), "no PARAM edge when reaching-def not found");
  }

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
    List<DdgEdge> localEdges = List.of(new DdgEdge(defA.id(), callSite.id(), new LocalEdge()));
    List<Map<String, Object>> calls = List.of(Map.of("from", caller, "to", callee));

    List<DdgEdge> result = builder.build(nodes, localEdges, calls);

    long paramCount = result.stream().filter(e -> e.edgeInfo() instanceof ParamEdge).count();
    long returnCount = result.stream().filter(e -> e.edgeInfo() instanceof ReturnEdge).count();

    assertEquals(1, paramCount, "one PARAM edge expected");
    assertEquals(1, returnCount, "one RETURN edge expected");
  }

  @Test
  void build_noCalls_noEdges() {
    List<DdgNode> nodes = List.of(node(CALLER, "s0", "a = 1", StmtKind.ASSIGN));
    List<DdgEdge> result = builder.build(nodes, List.of(), List.of());
    assertTrue(result.isEmpty());
  }
}
