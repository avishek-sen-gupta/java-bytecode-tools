package tools.bytecode;

import java.util.*;
import tools.bytecode.artifact.*;

public class BwdSliceBuilder {

  public Map<String, Object> build(Artifact artifact, String methodSig, String localVar) {
    Map<String, DdgNode> nodeIndex = buildNodeIndex(artifact.ddg().nodes());
    Map<String, List<String>> callerIndex = buildCallerIndex(artifact.calltree().edges());

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
          // Track the RHS of the field write: "obj.<C: T f> = val" -> extract "val"
          fromLocal = extractFieldWriteRhs(fromNode.stmt());
        } else {
          fromLocal = extractDefinedLocal(fromNode.stmt());
        }

        resultEdges.add(
            buildEdge(
                edge.from(), fromNode.method(), item.nodeId(), ddgNode.method(), edge.edgeInfo()));
        worklist.add(new WorklistItem(edge.from(), fromLocal));
      }

      // Cross boundary — parameter: IDENTITY stmt, check if localVar is @parameterN
      if (ddgNode.kind() == StmtKind.IDENTITY && isParamIdentity(ddgNode.stmt(), item.localVar())) {
        int paramIndex = extractParamIndex(ddgNode.stmt());
        for (String callerSig : callerIndex.getOrDefault(ddgNode.method(), List.of())) {
          nodeIndex.values().stream()
              .filter(n -> n.method().equals(callerSig))
              .filter(n -> isCallsiteTo(n, ddgNode.method()))
              .forEach(
                  callSiteNode -> {
                    String argLocal = extractArgLocal(callSiteNode.stmt(), paramIndex);
                    if (argLocal.isEmpty()) return;
                    resultEdges.add(
                        buildParamEdge(
                            callSiteNode.id(), callerSig, item.nodeId(), ddgNode.method()));
                    worklist.add(new WorklistItem(callSiteNode.id(), argLocal));
                  });
        }
      }

      // Cross boundary — return: ASSIGN_INVOKE callsite, follow callee's return stmts
      if (ddgNode.kind() == StmtKind.ASSIGN_INVOKE) {
        String calleeSig = ddgNode.call().get("targetMethodSignature");
        if (calleeSig != null) {
          nodeIndex.values().stream()
              .filter(n -> n.method().equals(calleeSig) && n.kind() == StmtKind.RETURN)
              .forEach(
                  returnNode -> {
                    String returnedLocal = extractReturnedLocal(returnNode.stmt());
                    resultEdges.add(
                        buildReturnEdge(
                            returnNode.id(), calleeSig, item.nodeId(), ddgNode.method()));
                    worklist.add(new WorklistItem(returnNode.id(), returnedLocal));
                  });
        }
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

  private Map<String, List<String>> buildCallerIndex(List<CalltreeEdge> edges) {
    Map<String, List<String>> index = new HashMap<>();
    for (CalltreeEdge edge : edges) {
      index.computeIfAbsent(edge.to(), k -> new ArrayList<>()).add(edge.from());
    }
    return index;
  }

  private List<DdgEdge> incomingEdges(List<DdgEdge> edges, String nodeId) {
    return edges.stream()
        .filter(e -> nodeId.equals(e.to()))
        .filter(e -> e.edgeInfo() instanceof LocalEdge || e.edgeInfo() instanceof HeapEdge)
        .toList();
  }

  private boolean isDefinitionOf(String stmt, String localVar) {
    return stmt.startsWith(localVar + " = ") || stmt.startsWith(localVar + " := ");
  }

  private boolean isParamIdentity(String stmt, String localVar) {
    return stmt.startsWith(localVar + " := @parameter");
  }

  private boolean isCallsiteTo(DdgNode node, String targetSig) {
    return (node.kind() == StmtKind.ASSIGN_INVOKE || node.kind() == StmtKind.INVOKE)
        && targetSig.equals(node.call().get("targetMethodSignature"));
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

  private int extractParamIndex(String stmt) {
    int start = stmt.indexOf("@parameter") + "@parameter".length();
    int end = stmt.indexOf(":", start);
    if (start < "@parameter".length() || end < 0) return -1;
    try {
      return Integer.parseInt(stmt.substring(start, end).trim());
    } catch (NumberFormatException e) {
      return -1;
    }
  }

  private String extractArgLocal(String stmt, int paramIndex) {
    int open = stmt.lastIndexOf('(');
    int close = stmt.lastIndexOf(')');
    if (open < 0 || close < 0 || close <= open) return "";
    String args = stmt.substring(open + 1, close).trim();
    if (args.isEmpty()) return "";
    String[] parts = args.split(",");
    if (paramIndex >= parts.length) return "";
    return parts[paramIndex].trim();
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
    String kind =
        switch (edgeInfo) {
          case LocalEdge e -> "LOCAL";
          case HeapEdge e -> "HEAP";
          case ParamEdge e -> "PARAM";
          case ReturnEdge e -> "RETURN";
        };
    Map<String, Object> edgeInfoMap = new LinkedHashMap<>();
    edgeInfoMap.put("kind", kind);
    if (edgeInfo instanceof HeapEdge he) edgeInfoMap.put("field", he.field());
    return Map.of(
        "from", Map.of("method", fromMethod, "stmtId", extractLocalId(fromId)),
        "to", Map.of("method", toMethod, "stmtId", extractLocalId(toId)),
        "edge_info", edgeInfoMap);
  }

  private Map<String, Object> buildParamEdge(
      String callerNodeId, String callerMethod, String calleeNodeId, String calleeMethod) {
    return Map.of(
        "from", Map.of("method", callerMethod, "stmtId", extractLocalId(callerNodeId)),
        "to", Map.of("method", calleeMethod, "stmtId", extractLocalId(calleeNodeId)),
        "edge_info", Map.of("kind", "PARAM"));
  }

  private Map<String, Object> buildReturnEdge(
      String calleeNodeId, String calleeMethod, String callerNodeId, String callerMethod) {
    return Map.of(
        "from", Map.of("method", calleeMethod, "stmtId", extractLocalId(calleeNodeId)),
        "to", Map.of("method", callerMethod, "stmtId", extractLocalId(callerNodeId)),
        "edge_info", Map.of("kind", "RETURN"));
  }

  private String extractLocalId(String compoundId) {
    int hash = compoundId.lastIndexOf('#');
    return hash >= 0 ? compoundId.substring(hash + 1) : compoundId;
  }

  private record WorklistItem(String nodeId, String localVar) {}
}
