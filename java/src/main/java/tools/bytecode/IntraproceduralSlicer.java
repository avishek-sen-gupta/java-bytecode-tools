package tools.bytecode;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Queue;
import java.util.Set;
import java.util.stream.Collectors;
import sootup.core.graph.StmtGraph;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.Body;
import sootup.core.model.SootMethod;
import sootup.core.types.ClassType;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

class IntraproceduralSlicer {

  private final JavaView view;
  private final MethodResolver resolver;

  IntraproceduralSlicer(JavaView view, MethodResolver resolver) {
    this.view = view;
    this.resolver = resolver;
  }

  Map<String, Object> trace(String className, int fromLine, int toLine) {
    ClassType classType = view.getIdentifierFactory().getClassType(className);
    JavaSootClass clazz =
        view.getClass(classType)
            .orElseThrow(() -> new RuntimeException("Class not found: " + className));

    List<SootMethod> candidateMethods = resolver.findMethodsContainingLine(clazz, toLine);
    if (candidateMethods.isEmpty()) {
      candidateMethods = resolver.findMethodsContainingLine(clazz, fromLine);
    }
    if (candidateMethods.isEmpty()) {
      throw new RuntimeException(
          "No method found containing line " + toLine + " or " + fromLine + " in " + className);
    }

    List<Map<String, Object>> allTraces =
        candidateMethods.stream()
            .flatMap(method -> buildMethodTrace(method, fromLine, toLine).stream())
            .collect(Collectors.toList());

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("class", className);
    result.put("fromLine", fromLine);
    result.put("toLine", toLine);
    result.put("traces", allTraces);
    return result;
  }

  private Optional<Map<String, Object>> buildMethodTrace(
      SootMethod method, int fromLine, int toLine) {
    Body body = method.getBody();
    StmtGraph<?> graph = body.getStmtGraph();
    Set<Stmt> fromStmts = new LinkedHashSet<>(StmtAnalyzer.stmtsAtLine(graph, fromLine));
    Set<Stmt> toStmts = new LinkedHashSet<>(StmtAnalyzer.stmtsAtLine(graph, toLine));
    if (toStmts.isEmpty()) return Optional.empty();

    List<Stmt> pathStmts =
        fromStmts.isEmpty()
            ? backtrack(graph, Collections.emptySet(), toStmts)
            : backtrack(graph, fromStmts, toStmts);
    if (pathStmts.isEmpty() && !fromStmts.isEmpty()) return Optional.empty();

    List<Map<String, Object>> stmtDetails = StmtAnalyzer.buildStmtDetails(pathStmts);
    List<Map<String, Object>> sourceTrace = StmtAnalyzer.deduplicateToSourceLines(stmtDetails);

    Map<String, Object> methodTrace = new LinkedHashMap<>();
    methodTrace.put("method", method.getName());
    methodTrace.put("methodSignature", method.getSignature().toString());
    methodTrace.put("stmtCount", pathStmts.size());
    methodTrace.put("sourceLineCount", sourceTrace.size());
    methodTrace.put("sourceTrace", sourceTrace);
    methodTrace.put("stmtDetails", stmtDetails);
    return Optional.of(methodTrace);
  }

  /**
   * BFS backward from {@code toStmts}, collecting all stmts on any path that reaches {@code
   * fromStmts}. Uses an imperative queue+visited pattern — this algorithm is inherently stateful
   * and has no idiomatic functional equivalent in Java.
   */
  private List<Stmt> backtrack(StmtGraph<?> graph, Set<Stmt> fromStmts, Set<Stmt> toStmts) {
    Map<Stmt, Stmt> parentMap = new LinkedHashMap<>();
    Queue<Stmt> queue = new ArrayDeque<>(toStmts);
    Set<Stmt> visited = new LinkedHashSet<>(toStmts);
    toStmts.forEach(s -> parentMap.put(s, null));

    Set<Stmt> reachedFrom = new LinkedHashSet<>();
    while (!queue.isEmpty()) {
      Stmt current = queue.poll();
      if (fromStmts.contains(current)) reachedFrom.add(current);
      for (Stmt pred : graph.predecessors(current)) {
        if (visited.add(pred)) {
          parentMap.put(pred, current);
          queue.add(pred);
        }
      }
    }

    if (reachedFrom.isEmpty() && !fromStmts.isEmpty()) return Collections.emptyList();

    Set<Stmt> onPath = new LinkedHashSet<>();
    Queue<Stmt> traceQueue = new ArrayDeque<>(reachedFrom);
    while (!traceQueue.isEmpty()) {
      Stmt s = traceQueue.poll();
      if (onPath.add(s)) {
        Stmt next = parentMap.get(s);
        if (next != null) traceQueue.add(next);
      }
    }
    return new ArrayList<>(onPath);
  }
}
