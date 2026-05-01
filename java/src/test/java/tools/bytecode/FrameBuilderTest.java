package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Paths;
import java.util.List;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import sootup.core.model.SootMethod;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.views.JavaView;

class FrameBuilderTest {

  private static FrameBuilder builder;
  private static SootMethod processOrder;

  @BeforeAll
  static void setUp() {
    String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    JavaView view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
    MethodResolver resolver = new MethodResolver(view);
    builder = new FrameBuilder();
    processOrder = resolver.resolveByName("com.example.app.OrderService", "processOrder");
  }

  @Nested
  class BuildFrame {
    @Test
    void setsClassAndMethodName() {
      CallFrame frame = builder.buildFrame(processOrder, processOrder.getSignature().toString());
      assertEquals("com.example.app.OrderService", frame.className());
      assertEquals("processOrder", frame.methodName());
    }

    @Test
    void setsPositiveEntryAndExitLines() {
      CallFrame frame = builder.buildFrame(processOrder, processOrder.getSignature().toString());
      assertTrue(frame.entryLine() > 0, "entryLine should be positive");
      assertTrue(frame.exitLine() >= frame.entryLine(), "exitLine should be >= entryLine");
    }

    @Test
    void populatesSourceTrace() {
      CallFrame frame = builder.buildFrame(processOrder, processOrder.getSignature().toString());
      assertFalse(frame.sourceTrace().isEmpty());
    }

    @Test
    void populatesStmtDetails() {
      CallFrame frame = builder.buildFrame(processOrder, processOrder.getSignature().toString());
      assertFalse(frame.stmtDetails().isEmpty());
    }

    @Test
    void sourceTraceEntriesHaveLineKey() {
      CallFrame frame = builder.buildFrame(processOrder, processOrder.getSignature().toString());
      assertTrue(frame.sourceTrace().stream().allMatch(e -> e.containsKey(StmtAnalyzer.KEY_LINE)));
    }
  }

  @Nested
  class BuildFlatFrame {
    @Test
    void setsClassAndMethodName() {
      CallFrame frame =
          builder.buildFlatFrame(processOrder, processOrder.getSignature().toString());
      assertEquals("com.example.app.OrderService", frame.className());
      assertEquals("processOrder", frame.methodName());
    }

    @Test
    void hasEmptyStmtDetails() {
      CallFrame frame =
          builder.buildFlatFrame(processOrder, processOrder.getSignature().toString());
      assertTrue(frame.stmtDetails().isEmpty());
    }

    @Test
    void sourceTraceContainsOnlyCallEntries() {
      CallFrame frame =
          builder.buildFlatFrame(processOrder, processOrder.getSignature().toString());
      frame
          .sourceTrace()
          .forEach(
              e ->
                  assertTrue(
                      e.containsKey(StmtAnalyzer.KEY_CALLS),
                      "Flat frame trace entries should have calls key"));
    }
  }
}
