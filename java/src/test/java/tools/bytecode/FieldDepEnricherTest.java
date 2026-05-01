package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;
import tools.bytecode.artifact.*;

class FieldDepEnricherTest {

  private static final String METHOD_A = "<com.example.A: void set(int)>";
  private static final String METHOD_B = "<com.example.B: int get()>";
  private static final String FIELD = "<com.example.A: int count>";

  private static DdgNode node(String methodSig, String localId, String stmt) {
    return new DdgNode(
        methodSig + "#" + localId, methodSig, localId, stmt, -1, StmtKind.ASSIGN, Map.of());
  }

  @Test
  void emitsHeapEdgeForAliasingFieldReadWritePair() {
    DdgNode writeNode2 = node(METHOD_A, "w0", "r0.<com.example.A: int count> = delta");
    DdgNode readNode2 = node(METHOD_B, "r0", "$count = r1.<com.example.A: int count>");

    DdgGraph ddg = new DdgGraph(List.of(writeNode2, readNode2), List.of());
    // AliasCheck that always returns true (may-alias)
    FieldDepEnricher enricher = new FieldDepEnricher((sigA, localA, sigB, localB) -> true);

    DdgGraph enriched = enricher.enrich(ddg, Set.of(METHOD_A, METHOD_B));

    assertEquals(1, enriched.edges().size());
    DdgEdge edge = enriched.edges().get(0);
    assertEquals(METHOD_A + "#w0", edge.from());
    assertEquals(METHOD_B + "#r0", edge.to());
    assertInstanceOf(HeapEdge.class, edge.edgeInfo());
    assertEquals("<com.example.A: int count>", ((HeapEdge) edge.edgeInfo()).field());
  }

  @Test
  void noEdgeWhenAliasCheckReturnsFalse() {
    DdgNode writeNode = node(METHOD_A, "w0", "r0.<com.example.A: int count> = delta");
    DdgNode readNode = node(METHOD_B, "r0", "$count = r1.<com.example.A: int count>");

    DdgGraph ddg = new DdgGraph(List.of(writeNode, readNode), List.of());
    // AliasCheck that always returns false (no alias)
    FieldDepEnricher enricher = new FieldDepEnricher((sigA, localA, sigB, localB) -> false);

    DdgGraph enriched = enricher.enrich(ddg, Set.of(METHOD_A, METHOD_B));

    assertTrue(enriched.edges().isEmpty(), "no heap edge expected when alias check returns false");
  }

  @Test
  void outOfScopeWriteExcludedInBoundedMode() {
    DdgNode writeNode = node(METHOD_A, "w0", "r0.<com.example.A: int count> = delta");
    DdgNode readNode = node(METHOD_B, "r0", "$count = r1.<com.example.A: int count>");

    DdgGraph ddg = new DdgGraph(List.of(writeNode, readNode), List.of());
    FieldDepEnricher enricher = new FieldDepEnricher((sigA, localA, sigB, localB) -> true);

    // METHOD_A not in scope — write node excluded
    DdgGraph enriched = enricher.enrich(ddg, Set.of(METHOD_B));

    assertTrue(enriched.edges().isEmpty(), "write node out of scope must be excluded");
  }

  @Test
  void inScopeWriteIncludedWhenBothInScope() {
    DdgNode writeNode = node(METHOD_A, "w0", "r0.<com.example.A: int count> = delta");
    DdgNode readNode = node(METHOD_B, "r0", "$count = r1.<com.example.A: int count>");

    DdgGraph ddg = new DdgGraph(List.of(writeNode, readNode), List.of());
    FieldDepEnricher enricher = new FieldDepEnricher((sigA, localA, sigB, localB) -> true);

    DdgGraph enriched = enricher.enrich(ddg, Set.of(METHOD_A, METHOD_B));

    assertEquals(1, enriched.edges().size());
  }

  @Test
  void existingEdgesArePreserved() {
    DdgNode writeNode = node(METHOD_A, "w0", "r0.<com.example.A: int count> = delta");
    DdgNode readNode = node(METHOD_B, "r0", "$count = r1.<com.example.A: int count>");
    DdgEdge existing = new DdgEdge(METHOD_A + "#w0", METHOD_A + "#w1", new LocalEdge());

    DdgGraph ddg = new DdgGraph(List.of(writeNode, readNode), List.of(existing));
    FieldDepEnricher enricher = new FieldDepEnricher((sigA, localA, sigB, localB) -> true);

    DdgGraph enriched = enricher.enrich(ddg, Set.of(METHOD_A, METHOD_B));

    assertEquals(2, enriched.edges().size());
    assertTrue(enriched.edges().contains(existing), "existing edge must be preserved");
  }

  @Test
  void doesNotMutateInputGraph() {
    DdgNode writeNode = node(METHOD_A, "w0", "r0.<com.example.A: int count> = delta");
    DdgNode readNode = node(METHOD_B, "r0", "$count = r1.<com.example.A: int count>");

    DdgGraph ddg = new DdgGraph(List.of(writeNode, readNode), List.of());
    FieldDepEnricher enricher = new FieldDepEnricher((sigA, localA, sigB, localB) -> true);

    enricher.enrich(ddg, Set.of(METHOD_A, METHOD_B));

    assertTrue(ddg.edges().isEmpty(), "input graph must not be mutated");
  }

  @Test
  void emptyDdgReturnsEmptyDdg() {
    DdgGraph ddg = new DdgGraph(List.of(), List.of());
    FieldDepEnricher enricher = new FieldDepEnricher((sigA, localA, sigB, localB) -> true);

    DdgGraph enriched = enricher.enrich(ddg, Set.of(METHOD_A));

    assertTrue(enriched.nodes().isEmpty());
    assertTrue(enriched.edges().isEmpty());
  }
}
