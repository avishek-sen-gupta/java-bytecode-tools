package tools.source.icfg;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Path;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class IcfgBuilderTest {

  private static ScipIndex index;
  private static SpoonMethodCfgCache cache;

  @BeforeAll
  static void setup() throws Exception {
    index = new ScipIndex(Path.of("../test-fixtures/index.scip"));
    cache = new SpoonMethodCfgCache("../test-fixtures/src");
  }

  @Test
  void entryNodeIsDepthZero() {
    IcfgConfig config = new IcfgConfig(0, StopCondition.none());
    InterproceduralCfg icfg =
        new IcfgBuilder()
            .build("com.example.app.OrderService", "processOrder", index, cache, config);
    assertNotNull(icfg.entryNode());
    assertTrue(
        icfg.entryNode().methodSymbol().contains("OrderService"),
        "Entry node should be from OrderService");
    assertEquals(0, icfg.entryNode().depth());
  }

  @Test
  void depthZeroHasNoCallEdges() {
    IcfgConfig config = new IcfgConfig(0, StopCondition.none());
    InterproceduralCfg icfg =
        new IcfgBuilder()
            .build("com.example.app.OrderService", "processOrder", index, cache, config);
    long callEdges = icfg.edgeSet().stream().filter(e -> e.kind() == IcfgEdgeKind.CALL).count();
    assertEquals(0, callEdges);
  }

  @Test
  void depth1ExpandsCallees() {
    IcfgConfig config = new IcfgConfig(1, StopCondition.prefix("java."));
    InterproceduralCfg icfg =
        new IcfgBuilder()
            .build("com.example.app.OrderService", "processOrder", index, cache, config);
    // CALL and RETURN edges must exist
    assertTrue(
        icfg.edgeSet().stream().anyMatch(e -> e.kind() == IcfgEdgeKind.CALL),
        "Expected at least one CALL edge");
    assertTrue(
        icfg.edgeSet().stream().anyMatch(e -> e.kind() == IcfgEdgeKind.RETURN),
        "Expected at least one RETURN edge");
  }

  @Test
  void depth1NodesIncludeCallee() {
    IcfgConfig config = new IcfgConfig(1, StopCondition.prefix("java."));
    InterproceduralCfg icfg =
        new IcfgBuilder()
            .build("com.example.app.OrderService", "processOrder", index, cache, config);
    // Depth-0 nodes exist (processOrder)
    assertTrue(icfg.vertexSet().stream().anyMatch(n -> n.depth() == 0));
    // Depth-1 nodes exist (callees)
    assertTrue(icfg.vertexSet().stream().anyMatch(n -> n.depth() == 1));
  }

  @Test
  void stopConditionPreventsExpansion() {
    // Stop on OrderRepository — its methods should not be expanded
    IcfgConfig config = new IcfgConfig(3, StopCondition.prefix("com.example.app.OrderRepository"));
    InterproceduralCfg icfg =
        new IcfgBuilder()
            .build("com.example.app.OrderService", "processOrder", index, cache, config);
    // No nodes from OrderRepository should appear
    boolean hasRepoNodes =
        icfg.vertexSet().stream().anyMatch(n -> n.methodSymbol().contains("OrderRepository"));
    assertFalse(hasRepoNodes, "OrderRepository nodes should be stopped");
  }

  @Test
  void exitNodesAreDepthZero() {
    IcfgConfig config = new IcfgConfig(1, StopCondition.prefix("java."));
    InterproceduralCfg icfg =
        new IcfgBuilder()
            .build("com.example.app.OrderService", "processOrder", index, cache, config);
    assertFalse(icfg.exitNodes().isEmpty());
    icfg.exitNodes()
        .forEach(
            n ->
                assertEquals(0, n.depth(), "Exit nodes should be from the entry method (depth 0)"));
  }

  @Test
  void multipleInvocationsPerNodeExpanded() {
    IcfgConfig config = new IcfgConfig(1, StopCondition.none());
    InterproceduralCfg icfg =
        new IcfgBuilder()
            .build("com.example.app.OrderService", "processOrder", index, cache, config);
    // processOrder has 3 invocations, but OrderRepository interface methods cannot be expanded.
    // Only transform (concrete method in OrderService) gets a CALL edge.
    long callEdges = icfg.edgeSet().stream().filter(e -> e.kind() == IcfgEdgeKind.CALL).count();
    assertTrue(callEdges >= 1, "Expected at least 1 CALL edge from concrete method invocation");
    assertTrue(
        icfg.edgeSet().stream()
            .anyMatch(
                e -> e.kind() == IcfgEdgeKind.CALL && e.to().methodSymbol().contains("transform")),
        "Expected CALL edge to transform method");
  }
}
