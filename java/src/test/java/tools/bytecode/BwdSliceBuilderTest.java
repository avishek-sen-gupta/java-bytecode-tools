package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.Test;

class BwdSliceBuilderTest {

  private static final String METHOD = "<com.example.Foo: void bar()>";

  // --- helpers ---

  private static Map<String, Object> stmtNode(String id, String stmt, String kind) {
    return Map.of("id", id, "node_type", "stmt", "stmt", stmt, "line", -1, "kind", kind);
  }

  private static Map<String, Object> ddgEdge(String from, String to) {
    return Map.of("from", from, "to", to, "edge_info", Map.of("kind", "ddg", "label", "ddg_next"));
  }

  private static Map<String, Object> payload(
      List<Map<String, Object>> nodes,
      List<Map<String, Object>> edges,
      List<String> entryIds,
      List<String> returnIds,
      List<String> callsiteIds) {
    Map<String, Object> m = new LinkedHashMap<>();
    m.put("nodes", nodes);
    m.put("edges", edges);
    m.put("entry_stmt_ids", entryIds);
    m.put("return_stmt_ids", returnIds);
    m.put("callsite_stmt_ids", callsiteIds);
    return m;
  }

  private static Map<String, Object> artifact(
      Map<String, Object> nodes, List<Map<String, Object>> calls, Map<String, Object> ddgs) {
    Map<String, Object> m = new LinkedHashMap<>();
    m.put("nodes", nodes);
    m.put("calls", calls);
    m.put("ddgs", ddgs);
    return m;
  }

  // --- tests ---

  @Test
  @SuppressWarnings("unchecked")
  void singleMethodArithmeticSlice() {
    // s0: a = 1
    // s1: b = 2
    // s2: $i0 = a + b   <- seed on $i0
    // DDG: s0 --ddg--> s2, s1 --ddg--> s2
    List<Map<String, Object>> nodes =
        List.of(
            stmtNode("s0", "a = 1", "assign"),
            stmtNode("s1", "b = 2", "assign"),
            stmtNode("s2", "$i0 = a + b", "assign"));
    List<Map<String, Object>> edges = List.of(ddgEdge("s0", "s2"), ddgEdge("s1", "s2"));
    Map<String, Object> ddgs =
        Map.of(METHOD, payload(nodes, edges, List.of(), List.of(), List.of()));
    Map<String, Object> art = artifact(Map.of(METHOD, Map.of()), List.of(), ddgs);

    Map<String, Object> result = new BwdSliceBuilder().build(art, METHOD, "$i0");

    List<Map<String, Object>> resultNodes = (List<Map<String, Object>>) result.get("nodes");
    List<Map<String, Object>> resultEdges = (List<Map<String, Object>>) result.get("edges");

    // All three stmts in the slice
    assertEquals(3, resultNodes.size());
    List<String> stmtIds =
        resultNodes.stream().map(n -> (String) n.get("stmtId")).sorted().toList();
    assertEquals(List.of("s0", "s1", "s2"), stmtIds);

    // Both upstream DDG edges present
    assertEquals(2, resultEdges.size());

    // Each result node carries its method and local_var
    resultNodes.forEach(n -> assertEquals(METHOD, n.get("method")));
    Map<String, Object> s2node =
        resultNodes.stream().filter(n -> "s2".equals(n.get("stmtId"))).findFirst().orElseThrow();
    assertEquals("$i0", s2node.get("local_var"));

    // seed block
    Map<String, Object> seed = (Map<String, Object>) result.get("seed");
    assertEquals(METHOD, seed.get("method"));
    assertEquals("$i0", seed.get("local_var"));
  }

  @Test
  void seedLocalNotFoundReturnsEmpty() {
    List<Map<String, Object>> nodes = List.of(stmtNode("s0", "a = 1", "assign"));
    Map<String, Object> ddgs =
        Map.of(METHOD, payload(nodes, List.of(), List.of(), List.of(), List.of()));
    Map<String, Object> art = artifact(Map.of(METHOD, Map.of()), List.of(), ddgs);

    Map<String, Object> result = new BwdSliceBuilder().build(art, METHOD, "nonexistent");

    List<?> resultNodes = (List<?>) result.get("nodes");
    List<?> resultEdges = (List<?>) result.get("edges");
    assertTrue(resultNodes.isEmpty(), "nodes should be empty");
    assertTrue(resultEdges.isEmpty(), "edges should be empty");
  }

  @Test
  @SuppressWarnings("unchecked")
  void crossMethodParameterCrossing() {
    // Caller method: calls bar(a) at s2, where a is defined at s1
    // s1 = "a = 1"  (assign)
    // s2 = "virtualinvoke r0.<Bar: void bar(int)>(a)"  (invoke)
    // DDG: s1 --ddg--> s2
    String CALLER = "<com.example.Caller: void main()>";
    String CALLEE = "<com.example.Bar: void bar(int)>";

    // Caller DDG payload
    List<Map<String, Object>> callerNodes =
        List.of(
            stmtNode("s1", "a = 1", "assign"),
            Map.of(
                "id",
                "s2",
                "node_type",
                "stmt",
                "stmt",
                "virtualinvoke r0.<com.example.Bar: void bar(int)>(a)",
                "line",
                -1,
                "kind",
                "invoke",
                "call",
                Map.of("targetMethodSignature", CALLEE)));
    List<Map<String, Object>> callerEdges = List.of(ddgEdge("s1", "s2"));
    Map<String, Object> callerPayload =
        payload(callerNodes, callerEdges, List.of(), List.of(), List.of("s2"));

    // Callee DDG payload — seed starts here
    // p0 = "@parameter0: int" identity stmt
    List<Map<String, Object>> calleeNodes =
        List.of(stmtNode("p0", "r1 := @parameter0: int", "identity"));
    Map<String, Object> calleePayload =
        payload(calleeNodes, List.of(), List.of("p0"), List.of(), List.of());

    // calls: CALLER -> CALLEE
    Map<String, Object> art =
        artifact(
            Map.of(CALLER, Map.of(), CALLEE, Map.of()),
            List.of(Map.of("from", CALLER, "to", CALLEE)),
            Map.of(CALLER, callerPayload, CALLEE, calleePayload));

    // Seed: in CALLEE on r1
    Map<String, Object> result = new BwdSliceBuilder().build(art, CALLEE, "r1");

    List<Map<String, Object>> resultNodes = (List<Map<String, Object>>) result.get("nodes");
    List<Map<String, Object>> resultEdges = (List<Map<String, Object>>) result.get("edges");

    // Should have: p0 (callee identity), s2 (caller call site), s1 (caller def of a)
    assertEquals(3, resultNodes.size());
    List<String> stmtIds =
        resultNodes.stream().map(n -> (String) n.get("stmtId")).sorted().toList();
    assertEquals(List.of("p0", "s1", "s2"), stmtIds);

    // Should have a param edge from s2 (caller) to p0 (callee)
    boolean hasParamEdge =
        resultEdges.stream()
            .anyMatch(
                e -> {
                  Map<?, ?> from = (Map<?, ?>) e.get("from");
                  Map<?, ?> to = (Map<?, ?>) e.get("to");
                  Map<?, ?> info = (Map<?, ?>) e.get("edge_info");
                  return CALLER.equals(from.get("method"))
                      && "s2".equals(from.get("stmtId"))
                      && CALLEE.equals(to.get("method"))
                      && "p0".equals(to.get("stmtId"))
                      && "param".equals(info.get("kind"));
                });
    assertTrue(hasParamEdge, "param edge from caller s2 to callee p0 expected");
  }
}
