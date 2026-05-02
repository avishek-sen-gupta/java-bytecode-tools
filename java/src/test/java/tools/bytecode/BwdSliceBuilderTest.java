package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.Test;
import tools.bytecode.artifact.*;

class BwdSliceBuilderTest {

  private static final String METHOD = "<com.example.Foo: void bar()>";

  // --- helpers ---

  private static DdgNode node(String methodSig, String localId, String stmt, StmtKind kind) {
    return new DdgNode(methodSig + "#" + localId, methodSig, localId, stmt, -1, kind, Map.of());
  }

  private static DdgNode callNode(String methodSig, String localId, String stmt, String targetSig) {
    return new DdgNode(
        methodSig + "#" + localId,
        methodSig,
        localId,
        stmt,
        -1,
        StmtKind.ASSIGN_INVOKE,
        Map.of("targetMethodSignature", targetSig));
  }

  private static DdgNode invokeNode(
      String methodSig, String localId, String stmt, String targetSig) {
    return new DdgNode(
        methodSig + "#" + localId,
        methodSig,
        localId,
        stmt,
        -1,
        StmtKind.INVOKE,
        Map.of("targetMethodSignature", targetSig));
  }

  private static DdgEdge localEdge(String fromMethod, String fromId, String toMethod, String toId) {
    return new DdgEdge(fromMethod + "#" + fromId, toMethod + "#" + toId, new LocalEdge());
  }

  private static DdgEdge heapEdge(
      String fromMethod, String fromId, String toMethod, String toId, String field) {
    return new DdgEdge(fromMethod + "#" + fromId, toMethod + "#" + toId, new HeapEdge(field));
  }

  private static Artifact artifact(
      List<CalltreeNode> calltreeNodes,
      List<CalltreeEdge> calltreeEdges,
      List<DdgNode> ddgNodes,
      List<DdgEdge> ddgEdges) {
    return new Artifact(
        Map.of("root", ""),
        new CalltreeGraph(calltreeNodes, calltreeEdges),
        new DdgGraph(ddgNodes, ddgEdges));
  }

  // --- tests ---

  @Test
  @SuppressWarnings("unchecked")
  void singleMethodArithmeticSlice() {
    // s0: a = 1
    // s1: b = 2
    // s2: $i0 = a + b   <- seed on $i0
    // DDG: s0 --local--> s2, s1 --local--> s2
    List<DdgNode> nodes =
        List.of(
            node(METHOD, "s0", "a = 1", StmtKind.ASSIGN),
            node(METHOD, "s1", "b = 2", StmtKind.ASSIGN),
            node(METHOD, "s2", "$i0 = a + b", StmtKind.ASSIGN));
    List<DdgEdge> edges =
        List.of(localEdge(METHOD, "s0", METHOD, "s2"), localEdge(METHOD, "s1", METHOD, "s2"));

    Artifact art =
        artifact(List.of(new CalltreeNode(METHOD, "Foo", "bar")), List.of(), nodes, edges);

    Map<String, Object> result = new BwdSliceBuilder().build(art, METHOD, "$i0");

    List<Map<String, Object>> resultNodes = (List<Map<String, Object>>) result.get("nodes");
    List<Map<String, Object>> resultEdges = (List<Map<String, Object>>) result.get("edges");

    assertEquals(3, resultNodes.size());
    List<String> stmtIds =
        resultNodes.stream().map(n -> (String) n.get("stmtId")).sorted().toList();
    assertEquals(List.of("s0", "s1", "s2"), stmtIds);
    assertEquals(2, resultEdges.size());
    resultNodes.forEach(n -> assertEquals(METHOD, n.get("method")));

    Map<String, Object> seed = (Map<String, Object>) result.get("seed");
    assertEquals(METHOD, seed.get("method"));
    assertEquals("$i0", seed.get("local_var"));
  }

  @Test
  void seedLocalNotFoundReturnsEmpty() {
    List<DdgNode> nodes = List.of(node(METHOD, "s0", "a = 1", StmtKind.ASSIGN));
    Artifact art =
        artifact(List.of(new CalltreeNode(METHOD, "Foo", "bar")), List.of(), nodes, List.of());

    Map<String, Object> result = new BwdSliceBuilder().build(art, METHOD, "nonexistent");

    assertTrue(((List<?>) result.get("nodes")).isEmpty());
    assertTrue(((List<?>) result.get("edges")).isEmpty());
  }

  @Test
  @SuppressWarnings("unchecked")
  void crossMethodParameterCrossing() {
    String CALLER = "<com.example.Caller: void main()>";
    String CALLEE = "<com.example.Bar: void bar(int)>";

    DdgNode defNode = node(CALLER, "s1", "a = 1", StmtKind.ASSIGN);
    DdgNode callSiteNode =
        invokeNode(CALLER, "s2", "virtualinvoke r0.<com.example.Bar: void bar(int)>(a)", CALLEE);
    DdgNode identityNode = node(CALLEE, "p0", "r1 := @parameter0: int", StmtKind.IDENTITY);

    List<DdgEdge> edges =
        List.of(
            localEdge(CALLER, "s1", CALLER, "s2"),
            // Pre-computed PARAM edge: reaching-def of 'a' → @parameter0 identity
            new DdgEdge(defNode.id(), identityNode.id(), new ParamEdge()));

    Artifact art =
        artifact(
            List.of(
                new CalltreeNode(CALLER, "Caller", "main"), new CalltreeNode(CALLEE, "Bar", "bar")),
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

  @Test
  @SuppressWarnings("unchecked")
  void followsHeapEdgeBackwardToFieldWrite() {
    // MethodA writes field; MethodB reads field; bwd-slice seeds at read, must reach write
    String MA = "<com.example.A: void setCount(int)>";
    String MB = "<com.example.B: int getCount()>";
    String FIELD = "<com.example.A: int count>";

    DdgNode writeNode = node(MA, "w0", "this.<com.example.A: int count> = delta", StmtKind.ASSIGN);
    DdgNode readNode = node(MB, "r0", "$count = this.<com.example.A: int count>", StmtKind.ASSIGN);
    DdgNode defNode = node(MB, "r1", "result = $count", StmtKind.ASSIGN);

    List<DdgEdge> edges =
        List.of(
            heapEdge(MA, "w0", MB, "r0", FIELD), // heap: write -> read
            localEdge(MB, "r0", MB, "r1")); // local: read -> result

    Artifact art =
        artifact(
            List.of(new CalltreeNode(MA, "A", "setCount"), new CalltreeNode(MB, "B", "getCount")),
            List.of(new CalltreeEdge(MA, MB)),
            List.of(writeNode, readNode, defNode),
            edges);

    // Seed at result = $count in MB
    Map<String, Object> result = new BwdSliceBuilder().build(art, MB, "result");

    List<Map<String, Object>> resultNodes = (List<Map<String, Object>>) result.get("nodes");
    List<Map<String, Object>> resultEdges = (List<Map<String, Object>>) result.get("edges");

    // Should reach: r1 (seed), r0 (local upstream), w0 (heap upstream)
    List<String> stmtIds =
        resultNodes.stream().map(n -> (String) n.get("stmtId")).sorted().toList();
    assertTrue(stmtIds.contains("w0"), "write node must be in slice: " + stmtIds);
    assertTrue(stmtIds.contains("r0"), "read node must be in slice: " + stmtIds);
    assertTrue(stmtIds.contains("r1"), "seed node must be in slice: " + stmtIds);

    boolean hasHeapEdge =
        resultEdges.stream()
            .anyMatch(
                e -> {
                  Map<?, ?> info = (Map<?, ?>) e.get("edge_info");
                  return "HEAP".equals(info.get("kind"));
                });
    assertTrue(hasHeapEdge, "HEAP edge must appear in slice output");
  }
}
