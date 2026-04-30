package tools.source.icfg;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Path;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class IcfgDotExporterTest {

  private static String dot;
  private static InterproceduralCfg icfg;

  @BeforeAll
  static void buildDot() throws Exception {
    ScipIndex index = new ScipIndex(Path.of("../test-fixtures/index.scip"));
    SpoonMethodCfgCache cache = new SpoonMethodCfgCache("../test-fixtures/src");
    IcfgConfig config = new IcfgConfig(1, StopCondition.prefix("java."));
    icfg =
        new IcfgBuilder()
            .build("com.example.app.OrderService", "processOrder", index, cache, config);
    dot = new IcfgDotExporter().toDot(icfg);
  }

  @Test
  void outputStartsWithDigraph() {
    assertTrue(dot.startsWith("digraph icfg {"), "DOT output should start with 'digraph icfg {'");
  }

  @Test
  void containsSubgraphCluster() {
    assertTrue(dot.contains("subgraph cluster_"), "Expected at least one subgraph cluster");
  }

  @Test
  void containsCallEdgeLabel() {
    assertTrue(dot.contains("label=\"call\""), "Expected 'label=\"call\"' for CALL edges");
  }

  @Test
  void containsReturnEdgeLabel() {
    assertTrue(dot.contains("label=\"return\""), "Expected 'label=\"return\"' for RETURN edges");
  }

  @Test
  void containsDashedStyle() {
    assertTrue(dot.contains("dashed"), "Expected dashed style for CALL/RETURN edges");
  }

  @Test
  void allNodesAppearInDot() {
    for (IcfgNode node : icfg.vertexSet()) {
      String id =
          "n_" + Math.abs(node.id().hashCode()) + "_" + node.id().replaceAll("[^a-zA-Z0-9_]", "_");
      assertTrue(dot.contains(id), "DOT should contain node ID: " + id);
    }
  }
}
