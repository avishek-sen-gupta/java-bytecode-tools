package tools.bytecode;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.Body;
import sootup.core.model.SootMethod;
import sootup.core.signatures.MethodSignature;

class FrameBuilder {

  CallFrame buildFrame(SootMethod method, String sig) {
    String methodClass = method.getDeclaringClassType().getFullyQualifiedName();
    Body body = method.getBody();
    List<Stmt> stmts = new ArrayList<>(body.getStmtGraph().getNodes());
    List<Map<String, Object>> details = StmtAnalyzer.buildStmtDetails(stmts);
    List<Map<String, Object>> srcTrace = StmtAnalyzer.deduplicateToSourceLines(details);
    int minL = StmtAnalyzer.minLine(stmts);
    int maxL = StmtAnalyzer.maxLine(stmts);
    return new CallFrame(methodClass, method.getName(), sig, minL, maxL, srcTrace, details);
  }

  /** Lightweight frame — only line ranges and a minimal sourceTrace for callSiteLine resolution. */
  CallFrame buildFlatFrame(SootMethod method, String sig) {
    String methodClass = method.getDeclaringClassType().getFullyQualifiedName();
    Body body = method.getBody();
    List<Stmt> stmts = new ArrayList<>(body.getStmtGraph().getNodes());
    int minL = StmtAnalyzer.minLine(stmts);
    int maxL = StmtAnalyzer.maxLine(stmts);
    List<Map<String, Object>> callTrace =
        stmts.stream()
            .flatMap(
                stmt -> {
                  int line = StmtAnalyzer.stmtLine(stmt);
                  if (line <= 0) return Stream.empty();
                  return StmtAnalyzer.extractInvoke(stmt).stream()
                      .map(
                          invoke -> {
                            MethodSignature callSig = invoke.getMethodSignature();
                            String callTarget =
                                callSig.getDeclClassType().getFullyQualifiedName()
                                    + "."
                                    + callSig.getName();
                            Map<String, Object> entry = new LinkedHashMap<>();
                            entry.put(StmtAnalyzer.KEY_LINE, line);
                            entry.put(StmtAnalyzer.KEY_CALLS, List.of(callTarget));
                            return entry;
                          });
                })
            .collect(Collectors.toList());
    return new CallFrame(methodClass, method.getName(), sig, minL, maxL, callTrace, List.of());
  }
}
