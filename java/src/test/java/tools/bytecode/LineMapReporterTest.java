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

class LineMapReporterTest {

  private static LineMapReporter reporter;
  private static final String ORDER_SERVICE = "com.example.app.OrderService";

  @BeforeAll
  static void setUp() {
    String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    JavaView view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
    reporter = new LineMapReporter(view, new StmtAnalyzer());
  }

  @Nested
  class DumpLineMap {
    @Test
    void returnsClassNameAndMethodCount() {
      Map<String, Object> result = reporter.dumpLineMap(ORDER_SERVICE);
      assertEquals(ORDER_SERVICE, result.get("class"));
      assertTrue(result.containsKey("methodCount"));
    }

    @Test
    void methodsListHasExpectedSize() {
      Map<String, Object> result = reporter.dumpLineMap(ORDER_SERVICE);
      @SuppressWarnings("unchecked")
      List<?> methods = (List<?>) result.get("methods");
      int methodCount = (int) result.get("methodCount");
      assertEquals(methodCount, methods.size());
    }

    @Test
    void eachMethodEntryHasRequiredKeys() {
      Map<String, Object> result = reporter.dumpLineMap(ORDER_SERVICE);
      @SuppressWarnings("unchecked")
      List<Map<String, Object>> methods = (List<Map<String, Object>>) result.get("methods");
      for (Map<String, Object> m : methods) {
        assertTrue(m.containsKey("method"), "missing 'method'");
        assertTrue(m.containsKey("lineStart"), "missing 'lineStart'");
        assertTrue(m.containsKey("lineEnd"), "missing 'lineEnd'");
        assertTrue(m.containsKey("stmtCount"), "missing 'stmtCount'");
        assertTrue(m.containsKey("lineMap"), "missing 'lineMap'");
      }
    }

    @Test
    void throws_whenClassNotFound() {
      assertThrows(RuntimeException.class, () -> reporter.dumpLineMap("com.example.NoSuch"));
    }
  }
}
