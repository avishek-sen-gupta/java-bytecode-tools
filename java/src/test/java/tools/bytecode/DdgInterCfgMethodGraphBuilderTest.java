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
        edges.stream()
            .anyMatch(edge -> "cfg".equals(((Map<?, ?>) edge.get("edge_info")).get("kind"))),
        "Expected at least one cfg edge");
    assertTrue(
        edges.stream()
            .anyMatch(edge -> "ddg".equals(((Map<?, ?>) edge.get("edge_info")).get("kind"))),
        "Expected at least one ddg edge");
    assertFalse(entryStmtIds.isEmpty(), "Expected entry statements");
    assertFalse(returnStmtIds.isEmpty(), "Expected return statements");
    assertFalse(callsiteStmtIds.isEmpty(), "Expected callsites");
  }
}
