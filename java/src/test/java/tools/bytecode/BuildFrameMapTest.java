package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class BuildFrameMapTest {

  private static final String SIG = "<com.example.Foo: void bar()>";

  private static BytecodeTracer.CallFrame frame(int entryLine, int exitLine) {
    return new BytecodeTracer.CallFrame(
        "com.example.Foo", "bar", SIG, entryLine, exitLine, List.of(), List.of());
  }

  @Nested
  class LightweightFrame {

    @Test
    void includesIdentityFields() {
      Map<String, Object> fm = BackwardTracer.buildLightweightFrameMap(frame(10, 20));

      assertEquals("com.example.Foo", fm.get("class"));
      assertEquals("bar", fm.get("method"));
      assertEquals(SIG, fm.get("methodSignature"));
    }

    @Test
    void includesLineMetadata() {
      Map<String, Object> fm = BackwardTracer.buildLightweightFrameMap(frame(10, 20));

      assertEquals(10, fm.get("lineStart"));
      assertEquals(20, fm.get("lineEnd"));
      assertEquals(11, fm.get("sourceLineCount"));
    }

    @Test
    void doesNotIncludeBlocksOrSourceTrace() {
      Map<String, Object> fm = BackwardTracer.buildLightweightFrameMap(frame(10, 20));

      assertNull(fm.get("blocks"));
      assertNull(fm.get("sourceTrace"));
      assertNull(fm.get("edges"));
      assertNull(fm.get("traps"));
    }

    @Test
    void doesNotIncludeRefMarker() {
      Map<String, Object> fm = BackwardTracer.buildLightweightFrameMap(frame(10, 20));

      assertNull(fm.get("ref"));
    }
  }

  @Nested
  class NestFrames {

    private static Map<String, Object> simpleFrame(String name) {
      return Map.of("method", name);
    }

    @Test
    void emptyListReturnsEmptyMap() {
      Map<String, Object> result = BackwardTracer.nestFrames(List.of());

      assertTrue(result.isEmpty());
    }

    @Test
    void singleFrameHasNoChildrenKey() {
      Map<String, Object> result = BackwardTracer.nestFrames(List.of(simpleFrame("A")));

      assertEquals("A", result.get("method"));
      assertNull(result.get("children"));
    }

    @Test
    void twoFramesNestedCorrectly() {
      Map<String, Object> result =
          BackwardTracer.nestFrames(List.of(simpleFrame("A"), simpleFrame("B")));

      assertEquals("A", result.get("method"));
      @SuppressWarnings("unchecked")
      List<Map<String, Object>> children = (List<Map<String, Object>>) result.get("children");
      assertNotNull(children);
      assertEquals(1, children.size());
      assertEquals("B", children.get(0).get("method"));
      assertNull(children.get(0).get("children"));
    }

    @Test
    void threeFramesNestedCorrectly() {
      Map<String, Object> result =
          BackwardTracer.nestFrames(List.of(simpleFrame("A"), simpleFrame("B"), simpleFrame("C")));

      assertEquals("A", result.get("method"));
      @SuppressWarnings("unchecked")
      List<Map<String, Object>> childrenA = (List<Map<String, Object>>) result.get("children");
      assertEquals("B", childrenA.get(0).get("method"));
      @SuppressWarnings("unchecked")
      List<Map<String, Object>> childrenB =
          (List<Map<String, Object>>) childrenA.get(0).get("children");
      assertEquals("C", childrenB.get(0).get("method"));
      assertNull(childrenB.get(0).get("children"));
    }

    @Test
    void preservesAllFrameFields() {
      Map<String, Object> frameA = Map.of("method", "A", "lineStart", 10, "lineEnd", 20);
      Map<String, Object> result = BackwardTracer.nestFrames(List.of(frameA));

      assertEquals(10, result.get("lineStart"));
      assertEquals(20, result.get("lineEnd"));
    }
  }
}
