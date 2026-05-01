package tools.bytecode;

import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import sootup.codepropertygraph.ddg.DdgCreator;
import sootup.codepropertygraph.propertygraph.PropertyGraph;
import sootup.codepropertygraph.propertygraph.edges.DdgEdge;
import sootup.codepropertygraph.propertygraph.edges.PropertyGraphEdge;
import sootup.codepropertygraph.propertygraph.nodes.StmtGraphNode;
import sootup.core.jimple.common.ref.JThisRef;
import sootup.core.jimple.common.stmt.JAssignStmt;
import sootup.core.jimple.common.stmt.JGotoStmt;
import sootup.core.jimple.common.stmt.JIdentityStmt;
import sootup.core.jimple.common.stmt.JIfStmt;
import sootup.core.jimple.common.stmt.JInvokeStmt;
import sootup.core.jimple.common.stmt.JReturnStmt;
import sootup.core.jimple.common.stmt.JReturnVoidStmt;
import sootup.core.jimple.common.stmt.JThrowStmt;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.jimple.javabytecode.stmt.JSwitchStmt;
import sootup.core.model.SootMethod;

public class DdgInterCfgMethodGraphBuilder {

  public Map<String, Object> build(SootMethod method) {
    List<Stmt> stmts = new ArrayList<>(method.getBody().getStmtGraph().getStmts());
    Map<Stmt, String> stmtIds = new IdentityHashMap<>();
    List<Map<String, Object>> nodes = new ArrayList<>();
    List<Map<String, Object>> edges = new ArrayList<>();
    List<String> entryStmtIds = new ArrayList<>();
    List<String> returnStmtIds = new ArrayList<>();
    List<String> callsiteStmtIds = new ArrayList<>();

    for (int i = 0; i < stmts.size(); i++) {
      Stmt stmt = stmts.get(i);
      String stmtId = "s" + i;
      stmtIds.put(stmt, stmtId);
      nodes.add(toNode(stmtId, stmt));
      if (stmt instanceof JIdentityStmt) {
        entryStmtIds.add(stmtId);
      }
      if (stmt instanceof JReturnStmt || stmt instanceof JReturnVoidStmt) {
        returnStmtIds.add(stmtId);
      }
      if (isCallsite(stmt)) {
        callsiteStmtIds.add(stmtId);
      }
    }

    for (Stmt stmt : stmts) {
      String fromId = stmtIds.get(stmt);
      for (Stmt successor : method.getBody().getStmtGraph().successors(stmt)) {
        edges.add(cfgEdge(fromId, stmtIds.get(successor)));
      }
    }

    PropertyGraph ddg = new DdgCreator().createGraph(method);
    for (PropertyGraphEdge edge : ddg.getEdges()) {
      if (!(edge instanceof DdgEdge)) {
        continue;
      }
      if (!(edge.getSource() instanceof StmtGraphNode)
          || !(edge.getDestination() instanceof StmtGraphNode)) {
        continue;
      }
      Stmt fromStmt = ((StmtGraphNode) edge.getSource()).getStmt();
      Stmt toStmt = ((StmtGraphNode) edge.getDestination()).getStmt();
      if (stmtIds.containsKey(fromStmt) && stmtIds.containsKey(toStmt)) {
        edges.add(ddgEdge(stmtIds.get(fromStmt), stmtIds.get(toStmt), edge.getLabel()));
      }
    }

    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("nodes", nodes);
    payload.put("edges", edges);
    payload.put("entry_stmt_ids", entryStmtIds);
    payload.put("return_stmt_ids", returnStmtIds);
    payload.put("callsite_stmt_ids", callsiteStmtIds);
    return payload;
  }

  private static Map<String, Object> toNode(String stmtId, Stmt stmt) {
    Map<String, Object> node = new LinkedHashMap<>();
    node.put("id", stmtId);
    node.put("node_type", "stmt");
    node.put("stmt", stmt.toString());
    node.put("line", StmtAnalyzer.stmtLine(stmt));
    node.put("kind", stmtKind(stmt));
    if (stmt instanceof JIdentityStmt identity && identity.getRightOp() instanceof JThisRef) {
      node.put("isThis", true);
    }
    if (isCallsite(stmt)) {
      node.put("call", Map.of("targetMethodSignature", extractInvokeTarget(stmt)));
    }
    return node;
  }

  private static Map<String, Object> cfgEdge(String from, String to) {
    return Map.of("from", from, "to", to, "edge_info", Map.of("kind", "cfg"));
  }

  private static Map<String, Object> ddgEdge(String from, String to, String label) {
    Map<String, Object> edgeInfo = new LinkedHashMap<>();
    edgeInfo.put("kind", "ddg");
    edgeInfo.put("label", label);
    return Map.of("from", from, "to", to, "edge_info", edgeInfo);
  }

  private static boolean isCallsite(Stmt stmt) {
    if (stmt instanceof JInvokeStmt) {
      return true;
    }
    return stmt instanceof JAssignStmt assign && assign.containsInvokeExpr();
  }

  private static String extractInvokeTarget(Stmt stmt) {
    if (stmt instanceof JInvokeStmt invokeStmt) {
      return invokeStmt
          .getInvokeExpr()
          .map(invoke -> invoke.getMethodSignature().toString())
          .orElse("");
    }
    if (stmt instanceof JAssignStmt assign && assign.containsInvokeExpr()) {
      return assign
          .getInvokeExpr()
          .map(invoke -> invoke.getMethodSignature().toString())
          .orElse("");
    }
    return "";
  }

  private static String stmtKind(Stmt stmt) {
    if (stmt instanceof JIdentityStmt) return "identity";
    if (stmt instanceof JAssignStmt assign && assign.containsInvokeExpr()) return "assign_invoke";
    if (stmt instanceof JInvokeStmt) return "invoke";
    if (stmt instanceof JAssignStmt) return "assign";
    if (stmt instanceof JIfStmt) return "if";
    if (stmt instanceof JReturnStmt) return "return";
    if (stmt instanceof JReturnVoidStmt) return "return_void";
    if (stmt instanceof JThrowStmt) return "throw";
    if (stmt instanceof JGotoStmt) return "goto";
    if (stmt instanceof JSwitchStmt) return "switch";
    return "other";
  }
}
