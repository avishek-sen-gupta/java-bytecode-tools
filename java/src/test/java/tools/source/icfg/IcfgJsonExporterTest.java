package tools.source.icfg;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Path;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class IcfgJsonExporterTest {

  private static JsonNode root;
  private static InterproceduralCfg icfg;

  @BeforeAll
  static void buildJson() throws Exception {
    ScipIndex index = new ScipIndex(Path.of("../test-fixtures/index.scip"));
    SpoonMethodCfgCache cache = new SpoonMethodCfgCache("../test-fixtures/src");
    IcfgConfig config = new IcfgConfig(1, StopCondition.prefix("java."));
    icfg =
        new IcfgBuilder()
            .build("com.example.app.OrderService", "processOrder", index, cache, config);
    String json = new IcfgJsonExporter().toJson(icfg);
    root = new ObjectMapper().readTree(json);
  }

  @Test
  void hasNodesArray() {
    assertTrue(root.has("nodes"));
    assertTrue(root.get("nodes").isArray());
    assertTrue(root.get("nodes").size() > 0);
  }

  @Test
  void hasEdgesArray() {
    assertTrue(root.has("edges"));
    assertTrue(root.get("edges").isArray());
    assertTrue(root.get("edges").size() > 0);
  }

  @Test
  void nodeHasRequiredFields() {
    JsonNode node = root.get("nodes").get(0);
    assertTrue(node.has("id"));
    assertTrue(node.has("label"));
    assertTrue(node.has("method"));
    assertTrue(node.has("depth"));
  }

  @Test
  void edgeHasRequiredFields() {
    JsonNode edge = root.get("edges").get(0);
    assertTrue(edge.has("from"));
    assertTrue(edge.has("to"));
    assertTrue(edge.has("kind"));
  }

  @Test
  void edgeKindIsValidEnum() {
    for (JsonNode edge : root.get("edges")) {
      String kind = edge.get("kind").asText();
      assertDoesNotThrow(
          () -> IcfgEdgeKind.valueOf(kind), "Edge kind '" + kind + "' is not a valid IcfgEdgeKind");
    }
  }

  @Test
  void nodeCountMatchesIcfg() {
    assertEquals(
        icfg.vertexSet().size(),
        root.get("nodes").size(),
        "JSON node count should match ICFG vertex count");
  }

  @Test
  void edgeCountMatchesIcfg() {
    assertEquals(
        icfg.edgeSet().size(),
        root.get("edges").size(),
        "JSON edge count should match ICFG edge count");
  }
}
