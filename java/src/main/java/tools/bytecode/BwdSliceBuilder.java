package tools.bytecode;

import java.util.*;

public class BwdSliceBuilder {

  @SuppressWarnings("unchecked")
  public Map<String, Object> build(
      Map<String, Object> artifact, String methodSig, String localVar) {
    Map<String, Map<String, Object>> ddgs = (Map<String, Map<String, Object>>) artifact.get("ddgs");
    List<Map<String, Object>> calls =
        (List<Map<String, Object>>) artifact.getOrDefault("calls", List.of());
    Map<String, List<String>> callerIndex = buildCallerIndex(calls);

    List<Map<String, Object>> resultNodes = new ArrayList<>();
    List<Map<String, Object>> resultEdges = new ArrayList<>();
    Set<String> visited = new HashSet<>();
    Deque<WorklistItem> worklist = new ArrayDeque<>();

    Map<String, Object> ddg = ddgs.get(methodSig);
    if (ddg != null) {
      findDefStmts(ddg, localVar)
          .forEach(stmtId -> worklist.add(new WorklistItem(methodSig, stmtId, localVar)));
    }

    while (!worklist.isEmpty()) {
      WorklistItem item = worklist.poll();
      String key = item.methodSig() + "#" + item.stmtId();
      if (!visited.add(key)) continue;

      Map<String, Object> ddgPayload = ddgs.get(item.methodSig());
      if (ddgPayload == null) continue;
      Map<String, Object> stmt = findNode(ddgPayload, item.stmtId());
      if (stmt == null) continue;

      resultNodes.add(buildResultNode(item.methodSig(), item.stmtId(), stmt, item.localVar()));

      // Intra-method: walk backward along DDG edges (find edges where to == stmtId)
      for (Map<String, Object> edge : incomingDdgEdges(ddgPayload, item.stmtId())) {
        String fromId = (String) edge.get("from");
        Map<String, Object> fromStmt = findNode(ddgPayload, fromId);
        if (fromStmt == null) continue;
        String fromLocal = extractDefinedLocal(fromStmt);
        resultEdges.add(buildDdgEdge(item.methodSig(), fromId, item.methodSig(), item.stmtId()));
        worklist.add(new WorklistItem(item.methodSig(), fromId, fromLocal));
      }
    }

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("seed", Map.of("method", methodSig, "local_var", localVar));
    result.put("nodes", resultNodes);
    result.put("edges", resultEdges);
    return result;
  }

  @SuppressWarnings("unchecked")
  private Map<String, List<String>> buildCallerIndex(List<Map<String, Object>> calls) {
    Map<String, List<String>> index = new HashMap<>();
    for (Map<String, Object> call : calls) {
      String to = (String) call.get("to");
      String from = (String) call.get("from");
      index.computeIfAbsent(to, k -> new ArrayList<>()).add(from);
    }
    return index;
  }

  @SuppressWarnings("unchecked")
  private List<String> findDefStmts(Map<String, Object> ddg, String localVar) {
    List<Map<String, Object>> nodes = (List<Map<String, Object>>) ddg.get("nodes");
    return nodes.stream()
        .filter(n -> isDefinitionOf((String) n.get("stmt"), localVar))
        .map(n -> (String) n.get("id"))
        .toList();
  }

  private boolean isDefinitionOf(String stmt, String localVar) {
    // Jimple assignment: "x = ...", identity: "x := @parameter0: ..."
    return stmt.startsWith(localVar + " = ") || stmt.startsWith(localVar + " := ");
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> findNode(Map<String, Object> ddg, String stmtId) {
    List<Map<String, Object>> nodes = (List<Map<String, Object>>) ddg.get("nodes");
    return nodes.stream().filter(n -> stmtId.equals(n.get("id"))).findFirst().orElse(null);
  }

  @SuppressWarnings("unchecked")
  private List<Map<String, Object>> incomingDdgEdges(Map<String, Object> ddg, String stmtId) {
    List<Map<String, Object>> edges = (List<Map<String, Object>>) ddg.get("edges");
    return edges.stream()
        .filter(e -> stmtId.equals(e.get("to")))
        .filter(e -> "ddg".equals(((Map<?, ?>) e.get("edge_info")).get("kind")))
        .toList();
  }

  private String extractDefinedLocal(Map<String, Object> stmt) {
    String text = (String) stmt.get("stmt");
    int eq = text.indexOf(" = ");
    int id = text.indexOf(" := ");
    int cut = (id >= 0 && (eq < 0 || id < eq)) ? id : eq;
    return cut >= 0 ? text.substring(0, cut) : text;
  }

  private Map<String, Object> buildResultNode(
      String methodSig, String stmtId, Map<String, Object> stmt, String localVar) {
    Map<String, Object> n = new LinkedHashMap<>();
    n.put("method", methodSig);
    n.put("stmtId", stmtId);
    n.put("stmt", stmt.get("stmt"));
    n.put("local_var", localVar);
    n.put("line", stmt.getOrDefault("line", -1));
    n.put("kind", stmt.get("kind"));
    return n;
  }

  private Map<String, Object> buildDdgEdge(
      String fromMethod, String fromStmt, String toMethod, String toStmt) {
    return Map.of(
        "from", Map.of("method", fromMethod, "stmtId", fromStmt),
        "to", Map.of("method", toMethod, "stmtId", toStmt),
        "edge_info", Map.of("kind", "ddg"));
  }

  private record WorklistItem(String methodSig, String stmtId, String localVar) {}
}
