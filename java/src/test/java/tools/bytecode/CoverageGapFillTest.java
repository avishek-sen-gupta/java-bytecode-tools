package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.*;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class CoverageGapFillTest {

  private final ForwardTracer tracer = new ForwardTracer();

  @Nested
  class BuildPredecessorMapTest {

    @Test
    void emptyMap() {
      var result = tracer.buildPredecessorMap(Map.of());
      assertTrue(result.isEmpty());
    }

    @Test
    void simpleChain() {
      // A→B→C
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("A", List.of("B"));
      succ.put("B", List.of("C"));
      succ.put("C", List.of());

      var pred = tracer.buildPredecessorMap(succ);
      assertEquals(Set.of("A"), pred.get("B"));
      assertEquals(Set.of("B"), pred.get("C"));
      assertNull(pred.get("A"));
    }

    @Test
    void fanOut() {
      // A→[B,C]
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("A", List.of("B", "C"));
      succ.put("B", List.of());
      succ.put("C", List.of());

      var pred = tracer.buildPredecessorMap(succ);
      assertEquals(Set.of("A"), pred.get("B"));
      assertEquals(Set.of("A"), pred.get("C"));
    }

    @Test
    void fanIn() {
      // A→C, B→C
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("A", List.of("C"));
      succ.put("B", List.of("C"));
      succ.put("C", List.of());

      var pred = tracer.buildPredecessorMap(succ);
      assertEquals(Set.of("A", "B"), pred.get("C"));
    }
  }

  @Nested
  class SourceLinesTest {

    @Test
    void extractsPositiveLines() {
      Map<String, Object> block =
          Map.of(
              "stmts",
              List.of(
                  Map.of("line", -1), Map.of("line", 14), Map.of("line", 14), Map.of("line", 15)));
      assertEquals(Set.of(14, 15), tracer.sourceLines(block));
    }

    @Test
    void emptyForAllNegative() {
      Map<String, Object> block = Map.of("stmts", List.of(Map.of("line", -1)));
      assertTrue(tracer.sourceLines(block).isEmpty());
    }

    @Test
    void emptyStmts() {
      Map<String, Object> block = Map.of("stmts", List.of());
      assertTrue(tracer.sourceLines(block).isEmpty());
    }
  }

  @Nested
  class FillCoverageGapsTest {

    @Test
    void noGaps() {
      // A→B→C, all covered
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("A", List.of("B"));
      succ.put("B", List.of("C"));
      succ.put("C", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      Set<String> covered = new LinkedHashSet<>(Set.of("A", "B", "C"));
      var result = tracer.fillCoverageGaps(covered, succ, pred, Set.of());
      assertEquals(Set.of("A", "B", "C"), result);
    }

    @Test
    void singleGap() {
      // A→B→C, covered={A,C} → fills B
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("A", List.of("B"));
      succ.put("B", List.of("C"));
      succ.put("C", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      Set<String> covered = new LinkedHashSet<>(List.of("A", "C"));
      var result = tracer.fillCoverageGaps(covered, succ, pred, Set.of());
      assertTrue(result.contains("B"), "B should be filled");
      assertEquals(Set.of("A", "B", "C"), result);
    }

    @Test
    void handlerEntryExcluded() {
      // A→H→C, covered={A,C}, handler={H} → H not filled
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("A", List.of("H"));
      succ.put("H", List.of("C"));
      succ.put("C", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      Set<String> covered = new LinkedHashSet<>(List.of("A", "C"));
      var result = tracer.fillCoverageGaps(covered, succ, pred, Set.of("H"));
      assertFalse(result.contains("H"), "handler entry should not be filled");
      assertEquals(Set.of("A", "C"), result);
    }

    @Test
    void noPredecessorCovered() {
      // X→B→C, covered={C}, X not covered → B not filled
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("X", List.of("B"));
      succ.put("B", List.of("C"));
      succ.put("C", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      Set<String> covered = new LinkedHashSet<>(List.of("C"));
      var result = tracer.fillCoverageGaps(covered, succ, pred, Set.of());
      assertFalse(result.contains("B"), "B has no covered predecessor");
    }

    @Test
    void noSuccessorCovered() {
      // A→B→X, covered={A}, X not covered → B not filled (B13 case)
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("A", List.of("B"));
      succ.put("B", List.of("X"));
      succ.put("X", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      Set<String> covered = new LinkedHashSet<>(List.of("A"));
      var result = tracer.fillCoverageGaps(covered, succ, pred, Set.of());
      assertFalse(result.contains("B"), "B has no covered successor");
    }

    @Test
    void multipleIterations() {
      // A→B→C→D, covered={A,D} → fills B then C (or C then B, order varies)
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("A", List.of("B"));
      succ.put("B", List.of("C"));
      succ.put("C", List.of("D"));
      succ.put("D", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      Set<String> covered = new LinkedHashSet<>(List.of("A", "D"));
      var result = tracer.fillCoverageGaps(covered, succ, pred, Set.of());
      assertTrue(result.contains("B"), "B should be filled");
      assertTrue(result.contains("C"), "C should be filled");
      assertEquals(Set.of("A", "B", "C", "D"), result);
    }

    @Test
    void emptyCoveredSet() {
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("A", List.of("B"));
      succ.put("B", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      var result = tracer.fillCoverageGaps(Set.of(), succ, pred, Set.of());
      assertTrue(result.isEmpty());
    }

    @Test
    void entryBlockWithCoveredSuccessor() {
      // ENTRY→A→B, covered={A,B}, ENTRY has no predecessors → ENTRY filled
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("ENTRY", List.of("A"));
      succ.put("A", List.of("B"));
      succ.put("B", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      Set<String> covered = new LinkedHashSet<>(List.of("A", "B"));
      var result = tracer.fillCoverageGaps(covered, succ, pred, Set.of());
      assertTrue(result.contains("ENTRY"), "entry block should be filled");
    }

    @Test
    void entryBlockWithNoCoveredSuccessor() {
      // ENTRY→X, covered={}, X not covered → ENTRY not filled
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("ENTRY", List.of("X"));
      succ.put("X", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      var result = tracer.fillCoverageGaps(Set.of(), succ, pred, Set.of());
      assertFalse(
          result.contains("ENTRY"), "entry block with no covered successor should not fill");
    }

    @Test
    void entryBlockHandlerNotFilled() {
      // ENTRY→A, covered={A}, ENTRY is a handler entry → not filled
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("ENTRY", List.of("A"));
      succ.put("A", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      Set<String> covered = new LinkedHashSet<>(List.of("A"));
      var result = tracer.fillCoverageGaps(covered, succ, pred, Set.of("ENTRY"));
      assertFalse(
          result.contains("ENTRY"), "handler entry should not be filled even as entry block");
    }

    @Test
    void doesNotMutateInput() {
      Map<String, List<String>> succ = new LinkedHashMap<>();
      succ.put("A", List.of("B"));
      succ.put("B", List.of("C"));
      succ.put("C", List.of());
      var pred = tracer.buildPredecessorMap(succ);

      Set<String> original = new LinkedHashSet<>(List.of("A", "C"));
      Set<String> snapshot = new LinkedHashSet<>(original);
      tracer.fillCoverageGaps(original, succ, pred, Set.of());
      assertEquals(snapshot, original, "input set should not be mutated");
    }
  }
}
