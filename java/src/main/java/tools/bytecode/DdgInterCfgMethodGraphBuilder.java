package tools.bytecode;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import sootup.analysis.intraprocedural.reachingdefs.ReachingDefs;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.Body;
import sootup.core.model.SootMethod;
import tools.bytecode.artifact.DdgEdge;
import tools.bytecode.artifact.DdgNode;
import tools.bytecode.artifact.LocalEdge;
import tools.bytecode.artifact.StmtKind;

public class DdgInterCfgMethodGraphBuilder {

  public record MethodDdgPayload(List<DdgNode> nodes, List<DdgEdge> edges) {}

  public MethodDdgPayload build(SootMethod method, String methodSig) {
    List<Stmt> stmts = new ArrayList<>(method.getBody().getStmtGraph().getNodes());

    Map<Stmt, String> stmtToLocalId = new HashMap<>();
    for (int i = 0; i < stmts.size(); i++) {
      stmtToLocalId.put(stmts.get(i), "s" + i);
    }

    List<DdgNode> nodes = new ArrayList<>();
    for (Stmt stmt : stmts) {
      String localId = stmtToLocalId.get(stmt);
      String compoundId = methodSig + "#" + localId;
      String stmtText = stmt.toString();
      StmtKind kind = classifyStmt(stmt);
      Map<String, String> call = extractCallInfo(stmt);
      int line = StmtAnalyzer.stmtLine(stmt);
      nodes.add(new DdgNode(compoundId, methodSig, localId, stmtText, line, kind, call));
    }

    List<DdgEdge> edges = buildDdgEdges(method.getBody(), stmtToLocalId, methodSig);

    return new MethodDdgPayload(nodes, edges);
  }

  private StmtKind classifyStmt(Stmt stmt) {
    String text = stmt.toString();
    if (text.contains(":= @parameter") || text.contains(":= @this")) return StmtKind.IDENTITY;
    if (text.startsWith("return ")) return StmtKind.RETURN;
    if ((text.startsWith("$") || text.matches("^[#\\w][\\w$#]* = .+")) && text.contains("invoke "))
      return StmtKind.ASSIGN_INVOKE;
    if (text.contains("invoke ")) return StmtKind.INVOKE;
    return StmtKind.ASSIGN;
  }

  private Map<String, String> extractCallInfo(Stmt stmt) {
    return StmtAnalyzer.extractInvoke(stmt)
        .map(invoke -> Map.of("targetMethodSignature", invoke.getMethodSignature().toString()))
        .orElse(Map.of());
  }

  private List<DdgEdge> buildDdgEdges(
      Body body, Map<Stmt, String> stmtToLocalId, String methodSig) {
    ReachingDefs rd = new ReachingDefs(body.getStmtGraph());
    Map<Stmt, List<Stmt>> defsByUse = rd.getReachingDefs();
    List<DdgEdge> edges = new ArrayList<>();
    for (var entry : defsByUse.entrySet()) {
      String toLocalId = stmtToLocalId.get(entry.getKey());
      if (toLocalId == null) continue;
      String toId = methodSig + "#" + toLocalId;
      for (Stmt defStmt : entry.getValue()) {
        String fromLocalId = stmtToLocalId.get(defStmt);
        if (fromLocalId == null) continue;
        String fromId = methodSig + "#" + fromLocalId;
        edges.add(new DdgEdge(fromId, toId, new LocalEdge()));
      }
    }
    return edges;
  }
}
