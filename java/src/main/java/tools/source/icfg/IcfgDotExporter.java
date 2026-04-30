package tools.source.icfg;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

public class IcfgDotExporter {

  public String toDot(InterproceduralCfg icfg) {
    StringBuilder sb = new StringBuilder();
    sb.append("digraph icfg {\n");
    sb.append("  rankdir=LR;\n");
    sb.append("  node [shape=box fontname=monospace];\n\n");

    // Group nodes by (methodSymbol, depth) → one subgraph cluster per method call instance
    Map<String, Set<IcfgNode>> clusters = new LinkedHashMap<>();
    for (IcfgNode node : icfg.vertexSet()) {
      String clusterKey = node.methodSymbol() + "@" + node.depth();
      clusters.computeIfAbsent(clusterKey, k -> new LinkedHashSet<>()).add(node);
    }

    for (Map.Entry<String, Set<IcfgNode>> entry : clusters.entrySet()) {
      String clusterKey = entry.getKey();
      Set<IcfgNode> clusterNodes = entry.getValue();
      IcfgNode representative = clusterNodes.iterator().next();
      String sanitized = clusterKey.replaceAll("[^a-zA-Z0-9_]", "_");
      String simpleMethod = simpleMethodName(representative.methodSymbol());
      int depth = representative.depth();

      sb.append("  subgraph cluster_").append(sanitized).append(" {\n");
      sb.append("    label=\"")
          .append(simpleMethod)
          .append(" (depth ")
          .append(depth)
          .append(")\";\n");

      for (IcfgNode node : clusterNodes) {
        sb.append("    ")
            .append(nodeId(node))
            .append(" [label=\"")
            .append(nodeLabel(node))
            .append("\"];\n");
      }
      sb.append("  }\n\n");
    }

    // Edges
    for (IcfgEdge edge : icfg.edgeSet()) {
      sb.append("  ").append(nodeId(edge.from())).append(" -> ").append(nodeId(edge.to()));
      switch (edge.kind()) {
        case CALL -> sb.append(" [style=dashed, color=blue, label=\"call\"]");
        case RETURN -> sb.append(" [style=dashed, color=gray, label=\"return\"]");
        case INTRA -> sb.append(" [color=black]");
      }
      sb.append(";\n");
    }

    sb.append("}\n");
    return sb.toString();
  }

  private String nodeId(IcfgNode node) {
    return "n_" + node.id().replaceAll("[^a-zA-Z0-9_]", "_");
  }

  private String nodeLabel(IcfgNode node) {
    var cfn = node.cfgNode();
    if (cfn.getStatement() == null) {
      return cfn.getKind().name();
    }
    int line =
        cfn.getStatement().getPosition().isValidPosition()
            ? cfn.getStatement().getPosition().getLine()
            : -1;
    String stmt = cfn.getStatement().toString().replace("\"", "\\\"").replace("\n", "\\n");
    return "[L" + line + "] " + stmt + "  (depth " + node.depth() + ")";
  }

  private String simpleMethodName(String symbol) {
    // symbol: "com/example/app/OrderService#processOrder"
    int hash = symbol.lastIndexOf('#');
    return hash >= 0 ? symbol.substring(hash + 1) : symbol;
  }
}
