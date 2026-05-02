package tools.bytecode;

import java.util.*;
import java.util.stream.Collectors;
import sootup.core.graph.StmtGraph;
import sootup.core.jimple.basic.StmtPositionInfo;
import sootup.core.jimple.common.expr.AbstractInvokeExpr;
import sootup.core.jimple.common.stmt.*;
import sootup.core.jimple.javabytecode.stmt.JSwitchStmt;
import sootup.core.model.Position;

final class StmtAnalyzer {

  static final String KEY_LINE = "line";
  static final String KEY_JIMPLE = "jimple";
  static final String KEY_CALL_TARGET = "callTarget";
  static final String KEY_CALL_ARGS = "callArgCount";
  static final String KEY_CALLS = "calls";
  static final String KEY_BRANCH = "branch";

  int stmtLine(Stmt stmt) {
    StmtPositionInfo posInfo = stmt.getPositionInfo();
    if (posInfo == null) return -1;
    Position pos = posInfo.getStmtPosition();
    if (pos == null) return -1;
    return pos.getFirstLine();
  }

  int minLine(Collection<Stmt> stmts) {
    return stmts.stream().mapToInt(this::stmtLine).filter(l -> l > 0).min().orElse(-1);
  }

  int maxLine(Collection<Stmt> stmts) {
    return stmts.stream().mapToInt(this::stmtLine).max().orElse(-1);
  }

  Optional<AbstractInvokeExpr> extractInvoke(Stmt stmt) {
    if (stmt instanceof JInvokeStmt) {
      return ((JInvokeStmt) stmt).getInvokeExpr();
    } else if (stmt instanceof JAssignStmt) {
      return ((JAssignStmt) stmt).getInvokeExpr();
    }
    return Optional.empty();
  }

  List<Stmt> stmtsAtLine(StmtGraph<?> graph, int line) {
    return graph.getNodes().stream()
        .filter(stmt -> stmtLine(stmt) == line)
        .collect(Collectors.toList());
  }

  List<Map<String, Object>> buildStmtDetails(List<Stmt> stmts) {
    return stmts.stream()
        .map(
            stmt -> {
              Map<String, Object> detail = new LinkedHashMap<>();
              detail.put(KEY_LINE, stmtLine(stmt));
              detail.put(KEY_JIMPLE, stmt.toString());

              Optional<AbstractInvokeExpr> invoke = extractInvoke(stmt);
              if (invoke.isPresent()) {
                var sig = invoke.get().getMethodSignature();
                detail.put(
                    KEY_CALL_TARGET,
                    sig.getDeclClassType().getFullyQualifiedName() + "." + sig.getName());
                detail.put(KEY_CALL_ARGS, invoke.get().getArgCount());
              }
              if (stmt instanceof JIfStmt) {
                detail.put(KEY_BRANCH, ((JIfStmt) stmt).getCondition().toString());
              } else if (stmt instanceof JSwitchStmt) {
                detail.put(KEY_BRANCH, "switch");
              }
              return detail;
            })
        .collect(Collectors.toList());
  }

  /**
   * Merges consecutive statements at the same source line into one entry. Uses a fold via
   * Stream.collect — accumulates into a growing list, merging into the last element when lines are
   * consecutive.
   */
  List<Map<String, Object>> deduplicateToSourceLines(List<Map<String, Object>> stmtDetails) {
    return stmtDetails.stream().collect(ArrayList::new, this::foldDetail, List::addAll);
  }

  private void foldDetail(List<Map<String, Object>> acc, Map<String, Object> detail) {
    int line = (int) detail.get(KEY_LINE);
    if (!acc.isEmpty() && (int) acc.get(acc.size() - 1).get(KEY_LINE) == line) {
      mergeDetail(acc.get(acc.size() - 1), detail);
    } else {
      acc.add(toEntry(detail));
    }
  }

  private Map<String, Object> toEntry(Map<String, Object> detail) {
    Map<String, Object> entry = new LinkedHashMap<>();
    entry.put(KEY_LINE, detail.get(KEY_LINE));
    if (detail.containsKey(KEY_CALL_TARGET)) {
      entry.put(KEY_CALLS, new ArrayList<>(List.of((String) detail.get(KEY_CALL_TARGET))));
    }
    if (detail.containsKey(KEY_BRANCH)) {
      entry.put(KEY_BRANCH, detail.get(KEY_BRANCH));
    }
    return entry;
  }

  private void mergeDetail(Map<String, Object> target, Map<String, Object> detail) {
    if (detail.containsKey(KEY_CALL_TARGET)) {
      @SuppressWarnings("unchecked")
      List<String> calls = (List<String>) target.computeIfAbsent(KEY_CALLS, k -> new ArrayList<>());
      calls.add((String) detail.get(KEY_CALL_TARGET));
    }
    if (detail.containsKey(KEY_BRANCH)) {
      target.put(KEY_BRANCH, detail.get(KEY_BRANCH));
    }
  }

  int findCallSiteLine(CallFrame caller, CallFrame callee) {
    String calleeTarget = callee.className() + "." + callee.methodName();

    // Exact match attempt
    int line =
        caller.sourceTrace().stream()
            .filter(entry -> entry.containsKey(KEY_CALLS))
            .flatMapToInt(
                entry -> {
                  @SuppressWarnings("unchecked")
                  List<String> calls = (List<String>) entry.get(KEY_CALLS);
                  if (calls.stream().anyMatch(call -> call.equals(calleeTarget))) {
                    return java.util.stream.IntStream.of((int) entry.get(KEY_LINE));
                  }
                  return java.util.stream.IntStream.empty();
                })
            .findFirst()
            .orElse(-1);

    if (line != -1) return line;

    // Fallback: match by method name only (interface→impl dispatch)
    return caller.sourceTrace().stream()
        .filter(entry -> entry.containsKey(KEY_CALLS))
        .flatMapToInt(
            entry -> {
              @SuppressWarnings("unchecked")
              List<String> calls = (List<String>) entry.get(KEY_CALLS);
              if (calls.stream().anyMatch(call -> call.endsWith("." + callee.methodName()))) {
                return java.util.stream.IntStream.of((int) entry.get(KEY_LINE));
              }
              return java.util.stream.IntStream.empty();
            })
        .findFirst()
        .orElse(-1);
  }
}
