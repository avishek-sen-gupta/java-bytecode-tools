package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class CallGraphBuilderTest {

  private final CallGraphBuilder builder = new CallGraphBuilder(null);

  private static final String BRIDGE =
      "<com.example.Dao: java.lang.Object lookup(java.lang.String)>";
  private static final String REAL = "<com.example.Dao: java.lang.String lookup(java.lang.String)>";
  private static final String CALLER = "<com.example.Svc: void process()>";

  @Nested
  class CollapseCallsiteBridges {

    @Test
    void noBridgesReturnsUnchanged() {
      Map<String, Map<String, Integer>> callsites = Map.of(CALLER, Map.of(REAL, 42));
      Map<String, Map<String, Integer>> result =
          builder.collapseCallsiteBridges(callsites, Set.of(), Map.of());
      assertEquals(callsites, result);
    }

    @Test
    void redirectsBridgeCalleeToRealTarget() {
      Map<String, Map<String, Integer>> callsites = Map.of(CALLER, Map.of(BRIDGE, 55));
      Map<String, List<String>> rawGraph = Map.of(BRIDGE, List.of(BRIDGE, REAL));

      Map<String, Map<String, Integer>> result =
          builder.collapseCallsiteBridges(callsites, Set.of(BRIDGE), rawGraph);

      assertTrue(result.containsKey(CALLER));
      assertEquals(55, result.get(CALLER).get(REAL));
      assertFalse(result.get(CALLER).containsKey(BRIDGE));
    }

    @Test
    void removesBridgeCallerEntries() {
      Map<String, Map<String, Integer>> callsites = new LinkedHashMap<>();
      callsites.put(BRIDGE, Map.of(REAL, 10));
      callsites.put(CALLER, Map.of(REAL, 42));

      Map<String, Map<String, Integer>> result =
          builder.collapseCallsiteBridges(callsites, Set.of(BRIDGE), Map.of());

      assertFalse(result.containsKey(BRIDGE));
      assertTrue(result.containsKey(CALLER));
    }

    @Test
    void preservesLineNumberFromOriginalCallsite() {
      Map<String, Map<String, Integer>> callsites = Map.of(CALLER, Map.of(BRIDGE, 77, REAL, 77));
      Map<String, List<String>> rawGraph = Map.of(BRIDGE, List.of(REAL));

      Map<String, Map<String, Integer>> result =
          builder.collapseCallsiteBridges(callsites, Set.of(BRIDGE), rawGraph);

      assertEquals(77, result.get(CALLER).get(REAL));
    }
  }

  @Nested
  class BuildCallGraphIntegration {

    @Test
    void producesNonEmptyGraphForTestFixtures() {
      String classpath = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
      BytecodeTracer tracer = new BytecodeTracer(classpath, "com.example.app", null);
      CallGraphBuilder cgBuilder = new CallGraphBuilder(tracer);

      CallGraphBuilder.CallGraphResult result = cgBuilder.buildCallGraph();

      assertFalse(result.graph().isEmpty(), "call graph should have entries");
      assertFalse(result.methodLines().isEmpty(), "method lines should be populated");
    }

    @Test
    void graphContainsExpectedCallerToCalleeEdge() {
      String classpath = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
      BytecodeTracer tracer = new BytecodeTracer(classpath, "com.example.app", null);
      CallGraphBuilder cgBuilder = new CallGraphBuilder(tracer);

      CallGraphBuilder.CallGraphResult result = cgBuilder.buildCallGraph();

      String processOrderSig = "<com.example.app.OrderService: java.lang.String processOrder(int)>";
      assertTrue(result.graph().containsKey(processOrderSig), "processOrder should be a caller");
      List<String> callees = result.graph().get(processOrderSig);
      assertTrue(
          callees.stream().anyMatch(c -> c.contains("findById")),
          "processOrder should call findById");
    }

    @Test
    void methodLinesHaveValidRanges() {
      String classpath = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
      BytecodeTracer tracer = new BytecodeTracer(classpath, "com.example.app", null);
      CallGraphBuilder cgBuilder = new CallGraphBuilder(tracer);

      CallGraphBuilder.CallGraphResult result = cgBuilder.buildCallGraph();

      for (var entry : result.methodLines().entrySet()) {
        CallGraphBuilder.MethodLineRange range = entry.getValue();
        assertTrue(range.lineStart() > 0, "lineStart should be positive for " + entry.getKey());
        assertTrue(
            range.lineEnd() >= range.lineStart(),
            "lineEnd should be >= lineStart for " + entry.getKey());
      }
    }
  }
}
