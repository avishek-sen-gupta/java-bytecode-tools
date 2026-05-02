package tools.bytecode;

import java.util.ArrayDeque;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Queue;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
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
  private final StmtAnalyzer stmtAnalyzer;

  IntraproceduralSlicer(JavaView view, MethodResolver resolver, StmtAnalyzer stmtAnalyzer) {
    this.view = view;
    this.resolver = resolver;
    this.stmtAnalyzer = stmtAnalyzer;
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
    Set<Stmt> fromStmts = new LinkedHashSet<>(stmtAnalyzer.stmtsAtLine(graph, fromLine));
    Set<Stmt> toStmts = new LinkedHashSet<>(stmtAnalyzer.stmtsAtLine(graph, toLine));
    if (toStmts.isEmpty()) return Optional.empty();

    List<Stmt> pathStmts =
        fromStmts.isEmpty()
            ? backtrack(graph, Collections.emptySet(), toStmts)
            : backtrack(graph, fromStmts, toStmts);
    if (pathStmts.isEmpty() && !fromStmts.isEmpty()) return Optional.empty();

    List<Map<String, Object>> stmtDetails = stmtAnalyzer.buildStmtDetails(pathStmts);
    List<Map<String, Object>> sourceTrace = stmtAnalyzer.deduplicateToSourceLines(stmtDetails);

    Map<String, Object> methodTrace = new LinkedHashMap<>();
    methodTrace.put("method", method.getName());
    methodTrace.put("methodSignature", method.getSignature().toString());
    methodTrace.put("stmtCount", pathStmts.size());
    methodTrace.put("sourceLineCount", sourceTrace.size());
    methodTrace.put("sourceTrace", sourceTrace);
    methodTrace.put("stmtDetails", stmtDetails);
    return Optional.of(methodTrace);
  }

  private List<Stmt> backtrack(StmtGraph<?> graph, Set<Stmt> fromStmts, Set<Stmt> toStmts) {
    Map<Stmt, Stmt> parentMap = bfsParents(graph, toStmts);
    Set<Stmt> reachedFrom =
        parentMap.keySet().stream()
            .filter(fromStmts::contains)
            .collect(Collectors.toCollection(LinkedHashSet::new));
    if (reachedFrom.isEmpty() && !fromStmts.isEmpty()) return Collections.emptyList();
    return reachedFrom.stream()
        .flatMap(root -> pathFromRoot(parentMap, root))
        .distinct()
        .collect(Collectors.toList());
  }

  /**
   * BFS backward from {@code seeds}; returns a map of each visited stmt → its successor toward a
   * seed (seeds themselves map to null). Uses an imperative queue+visited pattern — BFS is
   * inherently stateful and has no idiomatic functional equivalent in Java.
   */
  private static Map<Stmt, Stmt> bfsParents(StmtGraph<?> graph, Set<Stmt> seeds) {
    Map<Stmt, Stmt> parentMap = new LinkedHashMap<>();
    Queue<Stmt> queue = new ArrayDeque<>(seeds);
    Set<Stmt> visited = new LinkedHashSet<>(seeds);
    seeds.forEach(s -> parentMap.put(s, null));
    while (!queue.isEmpty()) {
      Stmt current = queue.poll();
      for (Stmt pred : graph.predecessors(current)) {
        if (visited.add(pred)) {
          parentMap.put(pred, current);
          queue.add(pred);
        }
      }
    }
    return parentMap;
  }

  /** Follows the parent-map chain from {@code root} until the chain ends at a seed stmt. */
  private static Stream<Stmt> pathFromRoot(Map<Stmt, Stmt> parentMap, Stmt root) {
    return Stream.iterate(root, Objects::nonNull, parentMap::get);
  }
}
