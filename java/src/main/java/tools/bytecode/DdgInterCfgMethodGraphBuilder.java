package tools.bytecode;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.SootMethod;
import tools.bytecode.artifact.DdgEdge;
import tools.bytecode.artifact.DdgNode;
import tools.bytecode.artifact.LocalEdge;
import tools.bytecode.artifact.StmtKind;

public class DdgInterCfgMethodGraphBuilder {

  public record MethodDdgPayload(List<DdgNode> nodes, List<DdgEdge> edges) {}

  private static final Pattern ASSIGN_LOCAL = Pattern.compile("^(\\w[\\w$]*) = (.+)$");
  private static final Pattern IDENTITY_LOCAL = Pattern.compile("^(\\w[\\w$]*) := .+$");
  private static final Pattern RETURN_VAL = Pattern.compile("^return (\\w[\\w$]*)$");

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

    List<DdgEdge> edges = buildDdgEdges(stmts, stmtToLocalId, methodSig);

    return new MethodDdgPayload(nodes, edges);
  }

  private StmtKind classifyStmt(Stmt stmt) {
    String text = stmt.toString();
    if (text.contains(":= @parameter") || text.contains(":= @this")) return StmtKind.IDENTITY;
    if (text.startsWith("return ")) return StmtKind.RETURN;
    if ((text.startsWith("$") || text.matches("^\\w[\\w$]* = .+")) && text.contains("invoke "))
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
      List<Stmt> stmts, Map<Stmt, String> stmtToLocalId, String methodSig) {
    Map<String, Stmt> localToDef = new HashMap<>();
    for (Stmt stmt : stmts) {
      String text = stmt.toString();
      Matcher assign = ASSIGN_LOCAL.matcher(text);
      Matcher identity = IDENTITY_LOCAL.matcher(text);
      if (assign.matches()) localToDef.put(assign.group(1), stmt);
      else if (identity.matches()) localToDef.put(identity.group(1), stmt);
    }

    List<DdgEdge> edges = new ArrayList<>();
    for (Stmt stmt : stmts) {
      String toId = methodSig + "#" + stmtToLocalId.get(stmt);
      for (String usedLocal : extractUsedLocals(stmt)) {
        Stmt defStmt = localToDef.get(usedLocal);
        if (defStmt == null) continue;
        String fromId = methodSig + "#" + stmtToLocalId.get(defStmt);
        edges.add(new DdgEdge(fromId, toId, new LocalEdge()));
      }
    }
    return edges;
  }

  private List<String> extractUsedLocals(Stmt stmt) {
    List<String> used = new ArrayList<>();
    String text = stmt.toString();

    Matcher ret = RETURN_VAL.matcher(text);
    if (ret.matches()) {
      used.add(ret.group(1));
      return used;
    }

    int eqIdx = text.indexOf(" = ");
    if (eqIdx >= 0) {
      String rhs = text.substring(eqIdx + 3);
      extractLocalsFromExpr(rhs, used);
    } else if (text.contains("invoke ")) {
      extractLocalsFromExpr(text, used);
    }
    return used;
  }

  private void extractLocalsFromExpr(String expr, List<String> out) {
    Pattern localRef = Pattern.compile("\\b([a-z$][\\w$]*)\\b");
    Matcher m = localRef.matcher(expr);
    while (m.find()) {
      String candidate = m.group(1);
      if (!isJimpleKeyword(candidate)) out.add(candidate);
    }
  }

  private boolean isJimpleKeyword(String s) {
    return switch (s) {
      case "staticinvoke",
          "virtualinvoke",
          "specialinvoke",
          "interfaceinvoke",
          "dynamicinvoke",
          "new",
          "newarray",
          "return",
          "if",
          "goto",
          "throw",
          "null",
          "true",
          "false" ->
          true;
      default -> false;
    };
  }
}
