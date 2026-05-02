package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class DiscoverReachableTest {

  private static final FilterConfig NO_FILTER = new FilterConfig(List.of(), List.of());
  private final ForwardTracer tracer = new ForwardTracer();

  @Nested
  class SimpleChainTest {

    @Test
    void discoversAllMethodsInChain() {
      // A → B → C
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of("B"));
      callGraph.put("B", List.of("C"));
      callGraph.put("C", List.of());
      Set<String> known = Set.of("A", "B", "C");

      DiscoveryResult result = tracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A", "B", "C"), result.normalMethods());
      // A has callee B (NORMAL)
      assertEquals(1, result.calleeMap().get("A").size());
      assertEquals("B", result.calleeMap().get("A").get(0).signature());
      assertEquals(Classification.NORMAL, result.calleeMap().get("A").get(0).classification());
      // B has callee C (NORMAL)
      assertEquals("C", result.calleeMap().get("B").get(0).signature());
      assertEquals(Classification.NORMAL, result.calleeMap().get("B").get(0).classification());
      // C has no callees
      assertTrue(result.calleeMap().get("C").isEmpty());
    }
  }

  @Nested
  class CycleTest {

    @Test
    void detectsCycleInPathAncestors() {
      // A → B → A (cycle)
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of("B"));
      callGraph.put("B", List.of("A"));
      Set<String> known = Set.of("A", "B");

      DiscoveryResult result = tracer.discoverReachable("A", callGraph, known, NO_FILTER);

      // Both are NORMAL (cycle is per-call-site, not per-method)
      assertEquals(Set.of("A", "B"), result.normalMethods());
      // B's callee A is classified CYCLE
      assertEquals(1, result.calleeMap().get("B").size());
      assertEquals("A", result.calleeMap().get("B").get(0).signature());
      assertEquals(Classification.CYCLE, result.calleeMap().get("B").get(0).classification());
    }

    @Test
    void selfRecursion() {
      // A → A
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of("A"));
      Set<String> known = Set.of("A");

      DiscoveryResult result = tracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A"), result.normalMethods());
      assertEquals(1, result.calleeMap().get("A").size());
      assertEquals(Classification.CYCLE, result.calleeMap().get("A").get(0).classification());
    }
  }

  @Nested
  class FilteredTest {

    @Test
    void unknownSignatureIsFiltered() {
      // A → B, but B not in knownSignatures
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of("B"));
      Set<String> known = Set.of("A");

      DiscoveryResult result = tracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A"), result.normalMethods());
      assertEquals(1, result.calleeMap().get("A").size());
      assertEquals(Classification.FILTERED, result.calleeMap().get("A").get(0).classification());
    }

    @Test
    void filterConfigRejectsClass() {
      // A → <com.ext.Lib: void foo()>, filter stops com.ext
      String calleeSig = "<com.ext.Lib: void foo()>";
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of(calleeSig));
      Set<String> known = Set.of("A", calleeSig);
      FilterConfig filter = new FilterConfig(List.of(), List.of("com.ext"));

      DiscoveryResult result = tracer.discoverReachable("A", callGraph, known, filter);

      assertEquals(Set.of("A"), result.normalMethods());
      assertEquals(Classification.FILTERED, result.calleeMap().get("A").get(0).classification());
    }
  }

  @Nested
  class DiamondTest {

    @Test
    void diamondVisitsSharedNodeOnce() {
      // A → B, A → C, B → D, C → D
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of("B", "C"));
      callGraph.put("B", List.of("D"));
      callGraph.put("C", List.of("D"));
      callGraph.put("D", List.of());
      Set<String> known = Set.of("A", "B", "C", "D");

      DiscoveryResult result = tracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A", "B", "C", "D"), result.normalMethods());
      // A has two callees, both NORMAL
      assertEquals(2, result.calleeMap().get("A").size());
      // D appears as NORMAL callee of both B and C
      assertEquals(Classification.NORMAL, result.calleeMap().get("B").get(0).classification());
      assertEquals(Classification.NORMAL, result.calleeMap().get("C").get(0).classification());
    }
  }

  @Nested
  class EmptyCalleesTest {

    @Test
    void leafMethodHasEmptyCalleeList() {
      Map<String, List<String>> callGraph = new LinkedHashMap<>();
      callGraph.put("A", List.of());
      Set<String> known = Set.of("A");

      DiscoveryResult result = tracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A"), result.normalMethods());
      assertTrue(result.calleeMap().get("A").isEmpty());
    }

    @Test
    void methodNotInCallGraphHasEmptyCalleeList() {
      // A is in known but not in call graph
      Map<String, List<String>> callGraph = Map.of();
      Set<String> known = Set.of("A");

      DiscoveryResult result = tracer.discoverReachable("A", callGraph, known, NO_FILTER);

      assertEquals(Set.of("A"), result.normalMethods());
      assertTrue(result.calleeMap().get("A").isEmpty());
    }
  }
}
