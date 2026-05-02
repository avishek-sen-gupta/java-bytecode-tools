package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.bytecode.artifact.DdgEdge;
import tools.bytecode.artifact.DdgNode;
import tools.bytecode.artifact.ReturnEdge;
import tools.bytecode.artifact.StmtKind;

class InterProcEdgeBuilderTest {

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

    List<DdgEdge> edges = InterProcEdgeBuilder.buildReturnEdges(nodes, calls);

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

    List<DdgEdge> edges = InterProcEdgeBuilder.buildReturnEdges(nodes, calls);

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

    List<DdgEdge> edges = InterProcEdgeBuilder.buildReturnEdges(nodes, calls);

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

    List<DdgEdge> edges = InterProcEdgeBuilder.buildReturnEdges(nodes, calls);

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
}
