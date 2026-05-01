package tools.bytecode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class DdgInterCfgArtifactBuilderTest {

  private static final String PROCESS_ORDER_SIG =
      "<com.example.app.OrderService: java.lang.String processOrder(int)>";
  private static final String REPO_FIND_BY_ID_SIG =
      "<com.example.app.OrderRepository: java.lang.String findById(int)>";
  private static final String MISSING_SIG = "<com.example.app.MissingService: void nope()>";

  private static BytecodeTracer tracer;

  @BeforeAll
  static void setUp() {
    String classpath = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    tracer = new BytecodeTracer(classpath, "com.example.app", null);
  }

  @Test
  void preservesNodesAndCallsAndAddsDdgsAndMetadata() {
    Map<String, Object> input = new LinkedHashMap<>();
    input.put(
        "nodes",
        Map.of(
            PROCESS_ORDER_SIG,
            Map.of(
                "node_type",
                "java_method",
                "class",
                "com.example.app.OrderService",
                "method",
                "processOrder",
                "methodSignature",
                PROCESS_ORDER_SIG)));
    input.put("calls", List.of());
    input.put("metadata", Map.of("tool", "calltree"));

    Map<String, Object> output = new DdgInterCfgArtifactBuilder(tracer).build(input);

    assertEquals(input.get("nodes"), output.get("nodes"));
    assertEquals(input.get("calls"), output.get("calls"));
    assertTrue(((Map<?, ?>) output.get("ddgs")).containsKey(PROCESS_ORDER_SIG));
    assertEquals("ddg-inter-cfg", ((Map<?, ?>) output.get("metadata")).get("tool"));
    assertEquals("calltree", ((Map<?, ?>) output.get("metadata")).get("inputTool"));
    assertEquals(1, ((Map<?, ?>) output.get("metadata")).get("methodCount"));
    assertEquals(1, ((Map<?, ?>) output.get("metadata")).get("ddgCount"));
  }

  @Test
  void rejectsMissingNodes() {
    IllegalArgumentException ex =
        assertThrows(
            IllegalArgumentException.class,
            () -> new DdgInterCfgArtifactBuilder(tracer).build(Map.of("calls", List.of())));
    assertTrue(ex.getMessage().contains("nodes"), ex.getMessage());
  }

  @Test
  void rejectsResolvedMethodWithoutBody() {
    IllegalArgumentException ex =
        assertThrows(
            IllegalArgumentException.class,
            () ->
                new DdgInterCfgArtifactBuilder(tracer)
                    .build(
                        Map.of(
                            "nodes",
                            Map.of(
                                REPO_FIND_BY_ID_SIG,
                                Map.of("methodSignature", REPO_FIND_BY_ID_SIG)))));
    assertTrue(ex.getMessage().contains("has no body"), ex.getMessage());
    assertTrue(ex.getMessage().contains(REPO_FIND_BY_ID_SIG), ex.getMessage());
  }

  @Test
  void rejectsUnresolvedMethodSignature() {
    RuntimeException ex =
        assertThrows(
            RuntimeException.class,
            () ->
                new DdgInterCfgArtifactBuilder(tracer)
                    .build(
                        Map.of(
                            "nodes", Map.of(MISSING_SIG, Map.of("methodSignature", MISSING_SIG)))));
    assertTrue(ex.getMessage().contains("Method not found"), ex.getMessage());
    assertTrue(ex.getMessage().contains(MISSING_SIG), ex.getMessage());
  }
}
