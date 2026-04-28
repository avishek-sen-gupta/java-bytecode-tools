package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class BuildFrameMapTest {

  private static final String SIG = "<com.example.Foo: void bar()>";

  private static BytecodeTracer.CallFrame frame(int entryLine, int exitLine) {
    return new BytecodeTracer.CallFrame(
        "com.example.Foo", "bar", SIG, entryLine, exitLine, List.of(), List.of());
  }

  @Nested
  class FirstVisit {

    @Test
    void includesLineMetadata() {
      Set<String> visited = new HashSet<>();
      Map<String, Object> fm = BackwardTracer.buildRefAwareFrameMap(frame(10, 20), visited, true);

      assertEquals(10, fm.get("lineStart"));
      assertEquals(20, fm.get("lineEnd"));
      assertEquals(11, fm.get("sourceLineCount"));
    }

    @Test
    void addsSignatureToVisited() {
      Set<String> visited = new HashSet<>();
      BackwardTracer.buildRefAwareFrameMap(frame(10, 20), visited, true);

      assertTrue(visited.contains(SIG));
    }

    @Test
    void doesNotMarkAsRef() {
      Set<String> visited = new HashSet<>();
      Map<String, Object> fm = BackwardTracer.buildRefAwareFrameMap(frame(10, 20), visited, true);

      assertNull(fm.get("ref"));
    }
  }

  @Nested
  class SubsequentVisit {

    @Test
    void includesLineMetadataEvenWhenAlreadySeen() {
      Set<String> visited = new HashSet<>();
      visited.add(SIG);
      Map<String, Object> fm = BackwardTracer.buildRefAwareFrameMap(frame(10, 20), visited, true);

      assertEquals(10, fm.get("lineStart"));
      assertEquals(20, fm.get("lineEnd"));
      assertEquals(11, fm.get("sourceLineCount"));
    }

    @Test
    void marksAsRef() {
      Set<String> visited = new HashSet<>();
      visited.add(SIG);
      Map<String, Object> fm = BackwardTracer.buildRefAwareFrameMap(frame(10, 20), visited, true);

      assertEquals(true, fm.get("ref"));
    }

    @Test
    void doesNotAddSignatureAgain() {
      Set<String> visited = new HashSet<>();
      visited.add(SIG);
      int sizeBefore = visited.size();
      BackwardTracer.buildRefAwareFrameMap(frame(10, 20), visited, true);

      assertEquals(sizeBefore, visited.size());
    }
  }

  @Nested
  class FlatMode {

    @Test
    void omitsSourceLineCountInFlatMode() {
      Set<String> visited = new HashSet<>();
      Map<String, Object> fm = BackwardTracer.buildRefAwareFrameMap(frame(10, 20), visited, false);

      assertNull(fm.get("sourceLineCount"));
    }

    @Test
    void stillIncludesLineStartAndEndInFlatMode() {
      Set<String> visited = new HashSet<>();
      Map<String, Object> fm = BackwardTracer.buildRefAwareFrameMap(frame(10, 20), visited, false);

      assertEquals(10, fm.get("lineStart"));
      assertEquals(20, fm.get("lineEnd"));
    }
  }
}
