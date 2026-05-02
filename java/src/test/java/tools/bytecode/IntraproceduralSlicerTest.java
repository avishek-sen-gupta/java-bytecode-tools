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
  private static StmtAnalyzer stmtAnalyzer;
  private static final String ORDER_SERVICE = "com.example.app.OrderService";

  @BeforeAll
  static void setUp() {
    String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    JavaView view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
    stmtAnalyzer = new StmtAnalyzer();
    resolver = new MethodResolver(view, stmtAnalyzer);
    slicer = new IntraproceduralSlicer(view, resolver, stmtAnalyzer);
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

  @Nested
  class BacktrackBehavior {

    @Test
    void trace_sameFromAndToLine_sourceTraceHasExactlyOneLine() {
      int line = anyLineIn(ORDER_SERVICE, "processOrder");
      Map<String, Object> result = slicer.trace(ORDER_SERVICE, line, line);
      @SuppressWarnings("unchecked")
      List<Map<String, Object>> traces = (List<Map<String, Object>>) result.get("traces");
      assertFalse(traces.isEmpty());
      List<?> sourceTrace = (List<?>) traces.get(0).get("sourceTrace");
      assertEquals(1, sourceTrace.size());
    }

    @Test
    void trace_boundedFromBeforeTo_hasPositiveStmtCount() {
      int minLine = minLineIn(ORDER_SERVICE, "processOrder");
      int maxLine = anyLineIn(ORDER_SERVICE, "processOrder");
      int stmtCount = totalStmtCount(slicer.trace(ORDER_SERVICE, minLine, maxLine));
      assertTrue(stmtCount > 0, "Expected bounded trace to contain at least one statement");
    }

    @Test
    void trace_bounded_toLineIsIncludedInSourceTrace() {
      int minLine = minLineIn(ORDER_SERVICE, "processOrder");
      int maxLine = anyLineIn(ORDER_SERVICE, "processOrder");
      List<Integer> lines = sourceLinesIn(slicer.trace(ORDER_SERVICE, minLine, maxLine));
      assertTrue(
          lines.contains(maxLine), "Expected toLine " + maxLine + " in sourceTrace " + lines);
    }
  }

  private static int anyLineIn(String className, String methodName) {
    return resolver
        .resolveByName(className, methodName)
        .getBody()
        .getStmtGraph()
        .getNodes()
        .stream()
        .mapToInt(stmtAnalyzer::stmtLine)
        .filter(l -> l > 0)
        .max()
        .orElseThrow();
  }

  private static int minLineIn(String className, String methodName) {
    return resolver
        .resolveByName(className, methodName)
        .getBody()
        .getStmtGraph()
        .getNodes()
        .stream()
        .mapToInt(stmtAnalyzer::stmtLine)
        .filter(l -> l > 0)
        .min()
        .orElseThrow();
  }

  @SuppressWarnings("unchecked")
  private static int totalStmtCount(Map<String, Object> result) {
    return ((List<Map<String, Object>>) result.get("traces"))
        .stream().mapToInt(t -> (int) t.get("stmtCount")).sum();
  }

  @SuppressWarnings("unchecked")
  private static List<Integer> sourceLinesIn(Map<String, Object> result) {
    return ((List<Map<String, Object>>) result.get("traces"))
        .stream()
            .flatMap(t -> ((List<Map<String, Object>>) t.get("sourceTrace")).stream())
            .map(entry -> (int) entry.get(StmtAnalyzer.KEY_LINE))
            .collect(java.util.stream.Collectors.toList());
  }
}
