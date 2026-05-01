package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Paths;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.views.JavaView;

class IntraproceduralSlicerTest {

  private static IntraproceduralSlicer slicer;
  private static MethodResolver resolver;
  private static final String ORDER_SERVICE = "com.example.app.OrderService";

  @BeforeAll
  static void setUp() {
    String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    JavaView view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
    resolver = new MethodResolver(view);
    slicer = new IntraproceduralSlicer(view, resolver);
  }

  @Nested
  class Trace {
    @Test
    void returnsResultWithClassAndLineFields() {
      int toLine = anyLineIn(ORDER_SERVICE, "processOrder");
      Map<String, Object> result = slicer.trace(ORDER_SERVICE, -1, toLine);
      assertEquals(ORDER_SERVICE, result.get("class"));
      assertEquals(-1, result.get("fromLine"));
      assertEquals(toLine, result.get("toLine"));
    }

    @Test
    void returnsNonEmptyTraces_whenToLineExistsInMethod() {
      int toLine = anyLineIn(ORDER_SERVICE, "processOrder");
      Map<String, Object> result = slicer.trace(ORDER_SERVICE, -1, toLine);
      @SuppressWarnings("unchecked")
      List<?> traces = (List<?>) result.get("traces");
      assertFalse(traces.isEmpty());
    }

    @Test
    void tracesContainMethodAndSourceTraceFields() {
      int toLine = anyLineIn(ORDER_SERVICE, "processOrder");
      Map<String, Object> result = slicer.trace(ORDER_SERVICE, -1, toLine);
      @SuppressWarnings("unchecked")
      List<Map<String, Object>> traces = (List<Map<String, Object>>) result.get("traces");
      Map<String, Object> first = traces.get(0);
      assertTrue(first.containsKey("method"));
      assertTrue(first.containsKey("sourceTrace"));
      assertTrue(first.containsKey("stmtDetails"));
    }

    @Test
    void throws_whenClassNotFound() {
      assertThrows(RuntimeException.class, () -> slicer.trace("com.example.NoSuch", -1, 10));
    }
  }

  private static int anyLineIn(String className, String methodName) {
    return resolver
        .resolveByName(className, methodName)
        .getBody()
        .getStmtGraph()
        .getNodes()
        .stream()
        .mapToInt(StmtAnalyzer::stmtLine)
        .filter(l -> l > 0)
        .max()
        .orElseThrow();
  }
}
