package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import sootup.core.graph.StmtGraph;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.SootMethod;
import sootup.core.types.ClassType;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

class StmtAnalyzerTest {

  private static final StmtAnalyzer analyzer = new StmtAnalyzer();
  private static JavaView view;
  private static List<Stmt> orderServiceStmts;

  @BeforeAll
  static void setUp() {
    String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
    ClassType type = view.getIdentifierFactory().getClassType("com.example.app.OrderService");
    JavaSootClass cls = view.getClass(type).orElseThrow();
    SootMethod method =
        cls.getMethods().stream()
            .filter(m -> m.getName().equals("processOrder") && m.hasBody())
            .findFirst()
            .orElseThrow();
    orderServiceStmts = new ArrayList<>(method.getBody().getStmtGraph().getNodes());
  }

  @Nested
  class BuildStmtDetails {
    @Test
    void returnsOneEntryPerStmt() {
      List<Map<String, Object>> details = analyzer.buildStmtDetails(orderServiceStmts);
      assertEquals(orderServiceStmts.size(), details.size());
    }

    @Test
    void everyEntryHasLineAndJimpleKeys() {
      List<Map<String, Object>> details = analyzer.buildStmtDetails(orderServiceStmts);
      assertTrue(details.stream().allMatch(d -> d.containsKey(StmtAnalyzer.KEY_LINE)));
      assertTrue(details.stream().allMatch(d -> d.containsKey(StmtAnalyzer.KEY_JIMPLE)));
    }

    @Test
    void doesNotMutateInput() {
      List<Stmt> copy = new ArrayList<>(orderServiceStmts);
      analyzer.buildStmtDetails(orderServiceStmts);
      assertEquals(copy, orderServiceStmts);
    }
  }

  @Nested
  class DeduplicateToSourceLines {
    @Test
    void mergesConsecutiveSameLineEntries() {
      List<Map<String, Object>> input =
          List.of(
              mapOf(StmtAnalyzer.KEY_LINE, 10, StmtAnalyzer.KEY_CALL_TARGET, "com.Foo.bar"),
              mapOf(StmtAnalyzer.KEY_LINE, 10, StmtAnalyzer.KEY_CALL_TARGET, "com.Foo.baz"),
              mapOf(StmtAnalyzer.KEY_LINE, 11));
      List<Map<String, Object>> result = analyzer.deduplicateToSourceLines(input);
      assertEquals(2, result.size());
      assertEquals(10, result.get(0).get(StmtAnalyzer.KEY_LINE));
      @SuppressWarnings("unchecked")
      List<String> calls = (List<String>) result.get(0).get(StmtAnalyzer.KEY_CALLS);
      assertEquals(2, calls.size());
    }

    @Test
    void doesNotMergeDifferentLines() {
      List<Map<String, Object>> input =
          List.of(mapOf(StmtAnalyzer.KEY_LINE, 10), mapOf(StmtAnalyzer.KEY_LINE, 11));
      assertEquals(2, analyzer.deduplicateToSourceLines(input).size());
    }
  }

  @Nested
  class MinMaxLine {
    @Test
    void minLine_returnsSmallestPositiveLine() {
      int min = analyzer.minLine(orderServiceStmts);
      assertTrue(min > 0);
      assertTrue(
          orderServiceStmts.stream()
              .mapToInt(analyzer::stmtLine)
              .filter(l -> l > 0)
              .allMatch(l -> l >= min));
    }

    @Test
    void maxLine_returnsLargestLine() {
      int max = analyzer.maxLine(orderServiceStmts);
      assertTrue(orderServiceStmts.stream().mapToInt(analyzer::stmtLine).allMatch(l -> l <= max));
    }

    @Test
    void minLine_isAtMostMaxLine() {
      assertTrue(analyzer.minLine(orderServiceStmts) <= analyzer.maxLine(orderServiceStmts));
    }
  }

  @Nested
  class StmtsAtLine {
    @Test
    void returnsStmtsAtGivenLine() {
      SootMethod method =
          view
              .getClass(view.getIdentifierFactory().getClassType("com.example.app.OrderService"))
              .orElseThrow()
              .getMethods()
              .stream()
              .filter(m -> m.getName().equals("processOrder") && m.hasBody())
              .findFirst()
              .orElseThrow();
      StmtGraph<?> graph = method.getBody().getStmtGraph();
      int anyLine =
          orderServiceStmts.stream()
              .mapToInt(analyzer::stmtLine)
              .filter(l -> l > 0)
              .findFirst()
              .orElseThrow();

      List<Stmt> result = analyzer.stmtsAtLine(graph, anyLine);

      assertFalse(result.isEmpty());
      assertTrue(result.stream().allMatch(s -> analyzer.stmtLine(s) == anyLine));
    }
  }

  @Nested
  class FindCallSiteLine {
    @Test
    void returnsLineOfExactCallTarget() {
      Map<String, Object> entry = new LinkedHashMap<>();
      entry.put(StmtAnalyzer.KEY_LINE, 42);
      entry.put(StmtAnalyzer.KEY_CALLS, List.of("com.example.app.OrderRepository.findById"));
      CallFrame caller =
          new CallFrame(
              "com.example.app.OrderService",
              "processOrder",
              "<sig>",
              40,
              60,
              List.of(entry),
              List.of());
      CallFrame callee =
          new CallFrame(
              "com.example.app.OrderRepository",
              "findById",
              "<sig2>",
              10,
              20,
              List.of(),
              List.of());

      assertEquals(42, analyzer.findCallSiteLine(caller, callee));
    }

    @Test
    void returnsNegativeOneWhenNoCallFound() {
      CallFrame caller = new CallFrame("com.A", "m", "<s>", 1, 5, List.of(), List.of());
      CallFrame callee = new CallFrame("com.B", "n", "<s>", 1, 5, List.of(), List.of());
      assertEquals(-1, analyzer.findCallSiteLine(caller, callee));
    }

    @Test
    void fallsBackToMethodNameSuffixMatch() {
      Map<String, Object> entry = new LinkedHashMap<>();
      entry.put(StmtAnalyzer.KEY_LINE, 55);
      entry.put(StmtAnalyzer.KEY_CALLS, List.of("com.example.app.SomeImpl.process"));
      CallFrame caller = new CallFrame("com.A", "m", "<s>", 50, 60, List.of(entry), List.of());
      CallFrame callee =
          new CallFrame("com.example.app.OtherImpl", "process", "<s>", 1, 5, List.of(), List.of());

      assertEquals(55, analyzer.findCallSiteLine(caller, callee));
    }
  }

  // Helper
  private static Map<String, Object> mapOf(Object... kvs) {
    Map<String, Object> m = new LinkedHashMap<>();
    for (int i = 0; i < kvs.length; i += 2) m.put((String) kvs[i], kvs[i + 1]);
    return m;
  }
}
