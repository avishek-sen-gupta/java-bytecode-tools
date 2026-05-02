package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Paths;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import sootup.core.model.SootMethod;
import sootup.core.types.ClassType;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

class ForwardTracerTest {

  private final ForwardTracer tracer = new ForwardTracer();

  @Nested
  class ExtractClassName {

    @Test
    void extractsSimpleClassName() {
      assertEquals("com.example.Foo", tracer.extractClassName("<com.example.Foo: void bar(int)>"));
    }

    @Test
    void extractsNestedClassName() {
      assertEquals(
          "com.example.Outer$Inner",
          tracer.extractClassName("<com.example.Outer$Inner: int compute()>"));
    }

    @Test
    void extractsDefaultPackageClassName() {
      assertEquals("Foo", tracer.extractClassName("<Foo: void main(java.lang.String[])>"));
    }
  }

  @Nested
  class ExtractMethodName {

    @Test
    void extractsSimpleMethodName() {
      assertEquals("bar", tracer.extractMethodName("<com.example.Foo: void bar(int)>"));
    }

    @Test
    void extractsInitMethodName() {
      assertEquals("<init>", tracer.extractMethodName("<com.example.Foo: void <init>()>"));
    }

    @Test
    void extractsMethodWithReturnType() {
      assertEquals(
          "process", tracer.extractMethodName("<com.example.Svc: java.lang.String process(int)>"));
    }
  }

  @Nested
  class BuildBlockTrace {

    private static JavaView view;
    private static SootMethod processOrderMethod;

    @BeforeAll
    static void setUp() {
      String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
      view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
      ClassType type = view.getIdentifierFactory().getClassType("com.example.app.OrderService");
      JavaSootClass cls = view.getClass(type).orElseThrow();
      processOrderMethod =
          cls.getMethods().stream()
              .filter(m -> m.getName().equals("processOrder") && m.hasBody())
              .findFirst()
              .orElseThrow();
    }

    @Test
    @SuppressWarnings("unchecked")
    void returnsBlocksAndEdgesKeys() {
      ForwardTracer ft =
          new ForwardTracer(
              new BytecodeTracer(
                  Paths.get("../test-fixtures/classes").toAbsolutePath().toString(),
                  "com.example.app",
                  null));
      Map<String, Object> result = ft.buildBlockTrace(processOrderMethod);

      assertTrue(result.containsKey("blocks"));
      assertTrue(result.containsKey("edges"));
      List<Map<String, Object>> blocks = (List<Map<String, Object>>) result.get("blocks");
      assertFalse(blocks.isEmpty(), "should have at least one block");
      assertTrue(blocks.get(0).containsKey("id"), "each block should have an id");
      assertTrue(blocks.get(0).containsKey("stmts"), "each block should have stmts");
    }

    @Test
    @SuppressWarnings("unchecked")
    void blocksHaveSequentialIds() {
      ForwardTracer ft =
          new ForwardTracer(
              new BytecodeTracer(
                  Paths.get("../test-fixtures/classes").toAbsolutePath().toString(),
                  "com.example.app",
                  null));
      Map<String, Object> result = ft.buildBlockTrace(processOrderMethod);

      List<Map<String, Object>> blocks = (List<Map<String, Object>>) result.get("blocks");
      for (int i = 0; i < blocks.size(); i++) {
        assertEquals("B" + i, blocks.get(i).get("id"));
      }
    }

    @Test
    @SuppressWarnings("unchecked")
    void edgesReferenceValidBlockIds() {
      ForwardTracer ft =
          new ForwardTracer(
              new BytecodeTracer(
                  Paths.get("../test-fixtures/classes").toAbsolutePath().toString(),
                  "com.example.app",
                  null));
      Map<String, Object> result = ft.buildBlockTrace(processOrderMethod);

      List<Map<String, Object>> blocks = (List<Map<String, Object>>) result.get("blocks");
      List<Map<String, Object>> edges = (List<Map<String, Object>>) result.get("edges");
      java.util.Set<String> blockIds = new java.util.HashSet<>();
      for (Map<String, Object> b : blocks) {
        blockIds.add((String) b.get("id"));
      }
      for (Map<String, Object> edge : edges) {
        assertTrue(blockIds.contains(edge.get("fromBlock")), "fromBlock must be a valid block ID");
        assertTrue(blockIds.contains(edge.get("toBlock")), "toBlock must be a valid block ID");
      }
    }
  }
}
