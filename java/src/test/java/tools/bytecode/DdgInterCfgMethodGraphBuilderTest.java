package tools.bytecode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Paths;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import sootup.core.jimple.common.ref.JParameterRef;
import sootup.core.jimple.common.ref.JThisRef;
import sootup.core.jimple.common.stmt.JIdentityStmt;
import sootup.core.model.SootMethod;

class DdgInterCfgMethodGraphBuilderTest {

  private static BytecodeTracer tracer;
  private static SootMethod processOrder;
  private static SootMethod handleException;

  @BeforeAll
  static void setUp() {
    String classpath = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    tracer = new BytecodeTracer(classpath, "com.example.app", null);
    processOrder = tracer.resolveMethodByName("com.example.app.OrderService", "processOrder");
    handleException =
        tracer.resolveMethodByName("com.example.app.ExceptionService", "handleException");
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
    assertEquals(
        expectedStmtIds(nodes.size()),
        nodes.stream().map(node -> (String) node.get("id")).collect(Collectors.toList()),
        "Expected contiguous method-local statement ids");
    assertEquals(
        nodes.size(),
        new LinkedHashSet<>(nodes.stream().map(node -> (String) node.get("id")).toList()).size(),
        "Expected unique statement ids");

    Map<String, Map<String, Object>> nodesById =
        nodes.stream().collect(Collectors.toMap(node -> (String) node.get("id"), node -> node));
    nodes.forEach(
        node -> {
          assertTrue(node.containsKey("id"), "Missing node id");
          assertTrue(node.containsKey("node_type"), "Missing node_type");
          assertTrue(node.containsKey("stmt"), "Missing stmt");
          assertTrue(node.containsKey("line"), "Missing line");
          assertTrue(node.containsKey("kind"), "Missing kind");
          assertEquals("stmt", node.get("node_type"), "Unexpected node_type");
          assertTrue(((String) node.get("id")).matches("s\\d+"), "Expected method-local stmt id");
          assertFalse(((String) node.get("stmt")).isBlank(), "Expected non-blank stmt");
          assertInstanceOf(Integer.class, node.get("line"), "Expected integer line");
          assertFalse(((String) node.get("kind")).isBlank(), "Expected non-blank kind");
        });

    assertTrue(
        edges.stream()
            .anyMatch(edge -> "cfg".equals(((Map<?, ?>) edge.get("edge_info")).get("kind"))),
        "Expected at least one cfg edge");
    assertTrue(
        edges.stream()
            .anyMatch(edge -> "ddg".equals(((Map<?, ?>) edge.get("edge_info")).get("kind"))),
        "Expected at least one ddg edge");
    edges.forEach(
        edge -> {
          assertTrue(nodesById.containsKey(edge.get("from")), "Edge source must reference a node");
          assertTrue(
              nodesById.containsKey(edge.get("to")), "Edge destination must reference a node");
          assertInstanceOf(Map.class, edge.get("edge_info"), "Expected edge_info map");
          assertTrue(
              Set.of("cfg", "ddg").contains(((Map<?, ?>) edge.get("edge_info")).get("kind")),
              "Unexpected edge kind");
        });

    assertFalse(entryStmtIds.isEmpty(), "Expected entry statements");
    assertEquals(
        entryStmtIds,
        expectedEntryStmtIds(processOrder, nodes),
        "entry_stmt_ids should match this/parameter identity nodes");

    assertFalse(returnStmtIds.isEmpty(), "Expected return statements");
    assertEquals(
        returnStmtIds,
        nodes.stream()
            .filter(
                node -> "return".equals(node.get("kind")) || "return_void".equals(node.get("kind")))
            .map(node -> (String) node.get("id"))
            .collect(Collectors.toList()),
        "return_stmt_ids should match emitted return nodes");

    assertFalse(callsiteStmtIds.isEmpty(), "Expected callsites");
    assertEquals(
        callsiteStmtIds,
        nodes.stream()
            .filter(
                node ->
                    "invoke".equals(node.get("kind")) || "assign_invoke".equals(node.get("kind")))
            .map(node -> (String) node.get("id"))
            .collect(Collectors.toList()),
        "callsite_stmt_ids should match emitted callsite nodes");
    callsiteStmtIds.forEach(
        stmtId -> {
          Object call = nodesById.get(stmtId).get("call");
          assertInstanceOf(Map.class, call, "Callsite node should include call payload");
          assertFalse(
              ((String) ((Map<?, ?>) call).get("targetMethodSignature")).isBlank(),
              "Callsite targetMethodSignature should be populated");
        });
  }

  @Test
  void excludesCaughtExceptionIdentityStatementsFromEntryStmtIds() {
    Map<String, Object> payload = new DdgInterCfgMethodGraphBuilder().build(handleException);

    @SuppressWarnings("unchecked")
    List<Map<String, Object>> nodes = (List<Map<String, Object>>) payload.get("nodes");
    @SuppressWarnings("unchecked")
    List<String> entryStmtIds = (List<String>) payload.get("entry_stmt_ids");

    assertEquals(
        expectedEntryStmtIds(handleException, nodes),
        entryStmtIds,
        "entry_stmt_ids should exclude caught-exception identity statements");
    assertTrue(
        nodes.stream()
            .filter(node -> "identity".equals(node.get("kind")))
            .map(node -> (String) node.get("id"))
            .anyMatch(stmtId -> !entryStmtIds.contains(stmtId)),
        "Expected at least one non-entry identity node from a caught exception");
  }

  private static List<String> expectedStmtIds(int size) {
    return IntStream.range(0, size).mapToObj(i -> "s" + i).collect(Collectors.toList());
  }

  private static List<String> expectedEntryStmtIds(
      SootMethod method, List<Map<String, Object>> emittedNodes) {
    List<String> stmtIds = expectedStmtIds(emittedNodes.size());
    List<sootup.core.jimple.common.stmt.Stmt> stmts = method.getBody().getStmtGraph().getStmts();
    return IntStream.range(0, stmts.size())
        .filter(i -> isEntryIdentity(stmts.get(i)))
        .mapToObj(stmtIds::get)
        .collect(Collectors.toList());
  }

  private static boolean isEntryIdentity(sootup.core.jimple.common.stmt.Stmt stmt) {
    if (!(stmt instanceof JIdentityStmt identity)) {
      return false;
    }
    return identity.getRightOp() instanceof JThisRef
        || identity.getRightOp() instanceof JParameterRef;
  }
}
