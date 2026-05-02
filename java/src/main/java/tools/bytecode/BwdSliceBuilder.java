package tools.bytecode;

import java.util.*;
import tools.bytecode.artifact.*;

public class BwdSliceBuilder {

  public Map<String, Object> build(Artifact artifact, String methodSig, String localVar) {
    Map<String, DdgNode> nodeIndex = buildNodeIndex(artifact.ddg().nodes());

    List<Map<String, Object>> resultNodes = new ArrayList<>();
    List<Map<String, Object>> resultEdges = new ArrayList<>();
    Set<String> visited = new HashSet<>();
    Deque<WorklistItem> worklist = new ArrayDeque<>();

    // Seed: find nodes in methodSig that define localVar
    nodeIndex.values().stream()
        .filter(n -> n.method().equals(methodSig))
        .filter(n -> isDefinitionOf(n.stmt(), localVar))
        .map(n -> new WorklistItem(n.id(), localVar))
        .forEach(worklist::add);

    while (!worklist.isEmpty()) {
      WorklistItem item = worklist.poll();
      if (!visited.add(item.nodeId())) continue;

      DdgNode ddgNode = nodeIndex.get(item.nodeId());
      if (ddgNode == null) continue;

      resultNodes.add(buildResultNode(ddgNode, item.localVar()));

      // Intra-method and cross-method: walk backward along LOCAL and HEAP edges
      for (DdgEdge edge : incomingEdges(artifact.ddg().edges(), item.nodeId())) {
        DdgNode fromNode = nodeIndex.get(edge.from());
        if (fromNode == null) continue;

        String fromLocal;
        if (edge.edgeInfo() instanceof HeapEdge heapEdge) {
          fromLocal = extractFieldWriteRhs(fromNode.stmt());
        } else if (edge.edgeInfo() instanceof ReturnEdge) {
          fromLocal = extractReturnedLocal(fromNode.stmt());
        } else {
          fromLocal = extractDefinedLocal(fromNode.stmt());
        }

        resultEdges.add(
            buildEdge(
                edge.from(), fromNode.method(), item.nodeId(), ddgNode.method(), edge.edgeInfo()));
        worklist.add(new WorklistItem(edge.from(), fromLocal));
      }
    }

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("seed", Map.of("method", methodSig, "local_var", localVar));
    result.put("nodes", resultNodes);
    result.put("edges", resultEdges);
    return result;
  }

  private Map<String, DdgNode> buildNodeIndex(List<DdgNode> nodes) {
    Map<String, DdgNode> index = new HashMap<>();
    for (DdgNode node : nodes) index.put(node.id(), node);
    return index;
  }

  private List<DdgEdge> incomingEdges(List<DdgEdge> edges, String nodeId) {
    return edges.stream().filter(e -> nodeId.equals(e.to())).toList();
  }

  private boolean isDefinitionOf(String stmt, String localVar) {
    return stmt.startsWith(localVar + " = ") || stmt.startsWith(localVar + " := ");
  }

  private String extractDefinedLocal(String stmt) {
    int eq = stmt.indexOf(" = ");
    int id = stmt.indexOf(" := ");
    int cut = (id >= 0 && (eq < 0 || id < eq)) ? id : eq;
    return cut >= 0 ? stmt.substring(0, cut) : stmt;
  }

  private String extractFieldWriteRhs(String stmt) {
    // "obj.<C: T f> = val" -> "val"
    int eq = stmt.lastIndexOf(" = ");
    return eq >= 0 ? stmt.substring(eq + 3).trim() : "";
  }

  private String extractReturnedLocal(String stmt) {
    String trimmed = stmt.trim();
    if (!trimmed.startsWith("return ")) return "";
    return trimmed.substring("return ".length()).trim();
  }

  private Map<String, Object> buildResultNode(DdgNode node, String localVar) {
    Map<String, Object> n = new LinkedHashMap<>();
    n.put("method", node.method());
    n.put("stmtId", node.stmtId());
    n.put("stmt", node.stmt());
    n.put("local_var", localVar);
    n.put("line", node.line());
    n.put("kind", node.kind().name());
    return n;
  }

  private Map<String, Object> buildEdge(
      String fromId, String fromMethod, String toId, String toMethod, EdgeInfo edgeInfo) {
    String kind = edgeInfo.kindName();
    Map<String, Object> edgeInfoMap = new LinkedHashMap<>();
    edgeInfoMap.put("kind", kind);
    if (edgeInfo instanceof HeapEdge he) edgeInfoMap.put("field", he.field());
    return Map.of(
        "from", Map.of("method", fromMethod, "stmtId", extractLocalId(fromId)),
        "to", Map.of("method", toMethod, "stmtId", extractLocalId(toId)),
        "edge_info", edgeInfoMap);
  }

  private String extractLocalId(String compoundId) {
    int hash = compoundId.lastIndexOf('#');
    return hash >= 0 ? compoundId.substring(hash + 1) : compoundId;
  }

  private record WorklistItem(String nodeId, String localVar) {}
}
