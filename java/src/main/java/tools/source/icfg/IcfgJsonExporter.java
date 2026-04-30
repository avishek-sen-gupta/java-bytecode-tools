package tools.source.icfg;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

public class IcfgJsonExporter {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  public String toJson(InterproceduralCfg icfg) {
    try {
      ObjectNode root = MAPPER.createObjectNode();
      ArrayNode nodes = root.putArray("nodes");
      ArrayNode edges = root.putArray("edges");

      for (IcfgNode node : icfg.vertexSet()) {
        ObjectNode n = nodes.addObject();
        n.put("id", node.id());
        n.put("label", nodeLabel(node));
        n.put("method", node.methodSymbol());
        n.put("depth", node.depth());
      }

      for (IcfgEdge edge : icfg.edgeSet()) {
        ObjectNode e = edges.addObject();
        e.put("from", edge.from().id());
        e.put("to", edge.to().id());
        e.put("kind", edge.kind().name());
      }

      return MAPPER.writerWithDefaultPrettyPrinter().writeValueAsString(root);
    } catch (Exception ex) {
      throw new RuntimeException("Failed to serialize ICFG to JSON", ex);
    }
  }

  private String nodeLabel(IcfgNode node) {
    var cfn = node.cfgNode();
    if (cfn.getStatement() == null) {
      return cfn.getKind().name();
    }
    var position = cfn.getStatement().getPosition();
    int line = (position != null && position.isValidPosition()) ? position.getLine() : -1;
    return "[L" + line + "] " + cfn.getStatement();
  }
}
