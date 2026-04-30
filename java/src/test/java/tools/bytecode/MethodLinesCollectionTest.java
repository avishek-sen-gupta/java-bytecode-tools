package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;

class MethodLinesCollectionTest {

  @Test
  void methodLinesEntryHasLineStartAndLineEnd() {
    var entry = new CallGraphBuilder.MethodLineRange(10, 25);
    assertEquals(10, entry.lineStart());
    assertEquals(25, entry.lineEnd());
  }

  @Test
  void callGraphResultCarriesMethodLines() {
    var lines =
        Map.of("<com.example.Foo: void bar()>", new CallGraphBuilder.MethodLineRange(10, 20));
    var result = new CallGraphBuilder.CallGraphResult(Map.of(), Map.of(), lines);
    assertEquals(10, result.methodLines().get("<com.example.Foo: void bar()>").lineStart());
  }
}
