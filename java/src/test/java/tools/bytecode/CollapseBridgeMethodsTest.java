package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class CollapseBridgeMethodsTest {

  private final CallGraphBuilder builder = new CallGraphBuilder(null);

  // Signatures for a covariant-return bridge scenario:
  //   CovService.fetchItem calls both bridge and real
  //   bridge (Object lookup) calls self + real
  //   real (String lookup) has no callees
  private static final String FETCH =
      "<com.example.CovService: java.lang.Object fetchItem(java.lang.String)>";
  private static final String BRIDGE =
      "<com.example.CovDao: java.lang.Object lookup(java.lang.String)>";
  private static final String REAL =
      "<com.example.CovDao: java.lang.String lookup(java.lang.String)>";

  @Nested
  class NoBridges {

    @Test
    void returnsGraphUnchanged() {
      Map<String, List<String>> graph =
          Map.of(
              "<com.example.Foo: void bar()>", List.of("<com.example.Bar: void baz()>"),
              "<com.example.Bar: void baz()>", List.of());

      Map<String, List<String>> result = builder.collapseBridgeMethods(graph, Set.of());

      assertEquals(graph, result);
    }
  }

  @Nested
  class WithBridge {

    private Map<String, List<String>> graphWithBridge() {
      return Map.of(
          FETCH, List.of(BRIDGE, REAL),
          BRIDGE, List.of(BRIDGE, REAL), // self-loop + real
          REAL, List.of());
    }

    @Test
    void bridgeRemovedFromGraph() {
      Map<String, List<String>> result =
          builder.collapseBridgeMethods(graphWithBridge(), Set.of(BRIDGE));

      assertFalse(result.containsKey(BRIDGE), "bridge entry removed");
    }

    @Test
    void callerRedirectedToReal() {
      Map<String, List<String>> result =
          builder.collapseBridgeMethods(graphWithBridge(), Set.of(BRIDGE));

      List<String> callees = result.get(FETCH);
      assertFalse(callees.contains(BRIDGE), "bridge callee replaced");
      assertTrue(callees.contains(REAL), "real callee retained");
    }

    @Test
    void noDuplicateCalleesAfterRedirect() {
      // fetchItem already had REAL as a callee; redirecting BRIDGE→REAL must not duplicate it
      Map<String, List<String>> result =
          builder.collapseBridgeMethods(graphWithBridge(), Set.of(BRIDGE));

      long count = result.get(FETCH).stream().filter(REAL::equals).count();
      assertEquals(1, count, "REAL appears exactly once");
    }

    @Test
    void realMethodRetained() {
      Map<String, List<String>> result =
          builder.collapseBridgeMethods(graphWithBridge(), Set.of(BRIDGE));

      assertTrue(result.containsKey(REAL), "real method entry kept");
    }

    @Test
    void doesNotMutateInput() {
      Map<String, List<String>> graph = new java.util.LinkedHashMap<>(graphWithBridge());
      Map<String, List<String>> graphCopy = Map.copyOf(graph);

      builder.collapseBridgeMethods(graph, Set.of(BRIDGE));

      assertEquals(graphCopy.keySet(), graph.keySet(), "input graph keys unchanged");
    }
  }
}
