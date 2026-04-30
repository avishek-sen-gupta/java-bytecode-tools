package tools.bytecode;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Path;
import java.util.*;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import sootup.core.graph.StmtGraph;
import sootup.core.inputlocation.AnalysisInputLocation;
import sootup.core.jimple.basic.StmtPositionInfo;
import sootup.core.jimple.common.expr.AbstractInvokeExpr;
import sootup.core.jimple.common.stmt.*;
import sootup.core.jimple.javabytecode.stmt.JSwitchStmt;
import sootup.core.model.Body;
import sootup.core.model.Position;
import sootup.core.model.SootMethod;
import sootup.core.signatures.MethodSignature;
import sootup.core.types.ClassType;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

/**
 * BytecodeTracer — shared infrastructure for bytecode analysis.
 *
 * <p>Holds the SootUp view, project class filtering, and utility methods used by {@link
 * CallGraphBuilder}, {@link ForwardTracer}, and {@link BackwardTracer}. Also provides
 * intraprocedural tracing ({@link #trace}) and the CLI entry point.
 */
public class BytecodeTracer {

  private static final Logger log = LoggerFactory.getLogger(BytecodeTracer.class);

  private final JavaView view;
  private Path callGraphCache;
  private String projectPrefix;

  public BytecodeTracer(String classPath) {
    List<AnalysisInputLocation> locations = new ArrayList<>();
    for (String path : classPath.split(":")) {
      if (!path.isBlank()) {
        System.err.println("[init] Registering classpath entry: " + path);
        locations.add(new JavaClassPathAnalysisInputLocation(path));
        System.err.println("[init] Registered.");
      }
    }
    System.err.println("[init] Building JavaView from " + locations.size() + " location(s)...");
    long t = System.currentTimeMillis();
    this.view = new JavaView(locations);
    System.err.println("[init] JavaView ready in " + (System.currentTimeMillis() - t) + "ms");
  }

  // ------------------------------------------------------------------
  // Configuration
  // ------------------------------------------------------------------

  public void setCallGraphCache(Path path) {
    this.callGraphCache = path;
  }

  public Path getCallGraphCache() {
    return callGraphCache;
  }

  public void setProjectPrefix(String prefix) {
    this.projectPrefix = prefix;
  }

  public List<JavaSootClass> getProjectClasses() {
    System.err.println("[init] Enumerating classes (prefix=" + projectPrefix + ")...");
    long t = System.currentTimeMillis();
    var stream = view.getClasses();
    if (projectPrefix != null && !projectPrefix.isEmpty()) {
      stream = stream.filter(c -> c.getType().getFullyQualifiedName().startsWith(projectPrefix));
    }
    List<JavaSootClass> result = stream.collect(Collectors.toList());
    System.err.println(
        "[init] Found " + result.size() + " classes in " + (System.currentTimeMillis() - t) + "ms");
    return result;
  }

  // ------------------------------------------------------------------
  // Records
  // ------------------------------------------------------------------

  record CallFrame(
      String className,
      String methodName,
      String methodSignature,
      int entryLine,
      int exitLine,
      List<Map<String, Object>> sourceTrace,
      List<Map<String, Object>> stmtDetails) {}

  public record FilterConfig(List<String> allow, List<String> stop) {
    boolean shouldRecurse(String className) {
      if (allow != null && !allow.isEmpty()) {
        boolean allowed = false;
        for (String prefix : allow) {
          if (className.startsWith(prefix)) {
            allowed = true;
            break;
          }
        }
        if (!allowed) return false;
      }
      if (stop != null && !stop.isEmpty()) {
        for (String prefix : stop) {
          if (className.startsWith(prefix)) return false;
        }
      }
      return true;
    }

    public static FilterConfig load(Path path) throws IOException {
      if (path == null) return new FilterConfig(null, null);
      ObjectMapper m = new ObjectMapper();
      @SuppressWarnings("unchecked")
      Map<String, List<String>> raw = m.readValue(path.toFile(), Map.class);
      return new FilterConfig(raw.get("allow"), raw.get("stop"));
    }
  }

  // ------------------------------------------------------------------
  // Shared utilities (package-visible for subclasses)
  // ------------------------------------------------------------------

  static int stmtLine(Stmt stmt) {
    StmtPositionInfo posInfo = stmt.getPositionInfo();
    if (posInfo == null) return -1;
    Position pos = posInfo.getStmtPosition();
    if (pos == null) return -1;
    return pos.getFirstLine();
  }

  static Optional<AbstractInvokeExpr> extractInvoke(Stmt stmt) {
    if (stmt instanceof JInvokeStmt) {
      return ((JInvokeStmt) stmt).getInvokeExpr();
    } else if (stmt instanceof JAssignStmt) {
      return ((JAssignStmt) stmt).getInvokeExpr();
    }
    return Optional.empty();
  }

  static int findCallSiteLine(CallFrame caller, CallFrame callee) {
    String calleeTarget = callee.className() + "." + callee.methodName();
    for (Map<String, Object> entry : caller.sourceTrace()) {
      @SuppressWarnings("unchecked")
      List<String> calls = (List<String>) entry.get("calls");
      if (calls != null) {
        for (String call : calls) {
          if (call.equals(calleeTarget)) {
            return (int) entry.get("line");
          }
        }
      }
    }
    // Fallback: match by method name only (interface→impl dispatch)
    for (Map<String, Object> entry : caller.sourceTrace()) {
      @SuppressWarnings("unchecked")
      List<String> calls = (List<String>) entry.get("calls");
      if (calls != null) {
        for (String call : calls) {
          if (call.endsWith("." + callee.methodName())) {
            return (int) entry.get("line");
          }
        }
      }
    }
    return -1;
  }

  /** Resolve a method in a class by name. Throws if not found or ambiguous. */
  SootMethod resolveMethodByName(String className, String methodName) {
    ClassType type = view.getIdentifierFactory().getClassType(className);
    Optional<JavaSootClass> clsOpt = view.getClass(type);
    if (clsOpt.isEmpty()) {
      throw new RuntimeException("Class not found: " + className);
    }
    List<SootMethod> matches =
        clsOpt.get().getMethods().stream()
            .filter(m -> m.getName().equals(methodName) && m.hasBody())
            .collect(Collectors.toList());
    if (matches.isEmpty()) {
      throw new RuntimeException("No method named '" + methodName + "' in " + className);
    }
    if (matches.size() > 1) {
      StringBuilder sb = new StringBuilder();
      sb.append("Ambiguous: ")
          .append(matches.size())
          .append(" overloads for '")
          .append(methodName)
          .append("' in ")
          .append(className)
          .append(":\n");
      for (SootMethod m : matches) {
        int lineStart =
            m.getBody().getStmtGraph().getNodes().stream()
                .mapToInt(BytecodeTracer::stmtLine)
                .filter(l -> l > 0)
                .min()
                .orElse(-1);
        sb.append("  ").append(m.getSignature()).append(" (line ").append(lineStart).append(")\n");
      }
      sb.append("Use --from-line to disambiguate.");
      throw new RuntimeException(sb.toString());
    }
    return matches.get(0);
  }

  /** Resolve a method in a class by line number. Throws if not found. */
  SootMethod resolveMethod(String className, int line) {
    ClassType type = view.getIdentifierFactory().getClassType(className);
    Optional<JavaSootClass> clsOpt = view.getClass(type);
    if (clsOpt.isEmpty()) {
      throw new RuntimeException("Class not found: " + className);
    }
    List<SootMethod> methods = findMethodsContainingLine(clsOpt.get(), line);
    if (methods.isEmpty()) {
      throw new RuntimeException("No method containing line " + line + " in " + className);
    }
    return methods.get(0);
  }

  CallFrame buildFrame(SootMethod method, String sig) {
    String methodClass = method.getDeclaringClassType().getFullyQualifiedName();
    Body body = method.getBody();
    List<Stmt> stmts = new ArrayList<>(body.getStmtGraph().getNodes());
    List<Map<String, Object>> details = buildStmtDetails(stmts);
    List<Map<String, Object>> srcTrace = deduplicateToSourceLines(details);
    int minL =
        stmts.stream().mapToInt(BytecodeTracer::stmtLine).filter(l -> l > 0).min().orElse(-1);
    int maxL = stmts.stream().mapToInt(BytecodeTracer::stmtLine).max().orElse(-1);
    return new CallFrame(methodClass, method.getName(), sig, minL, maxL, srcTrace, details);
  }

  /** Lightweight frame — only line ranges and a minimal sourceTrace for callSiteLine resolution. */
  CallFrame buildFlatFrame(SootMethod method, String sig) {
    String methodClass = method.getDeclaringClassType().getFullyQualifiedName();
    Body body = method.getBody();
    List<Stmt> stmts = new ArrayList<>(body.getStmtGraph().getNodes());
    int minL =
        stmts.stream().mapToInt(BytecodeTracer::stmtLine).filter(l -> l > 0).min().orElse(-1);
    int maxL = stmts.stream().mapToInt(BytecodeTracer::stmtLine).max().orElse(-1);
    // Build a minimal sourceTrace with just call info (for callSiteLine resolution)
    List<Map<String, Object>> callTrace = new ArrayList<>();
    for (Stmt stmt : stmts) {
      Optional<AbstractInvokeExpr> invokeOpt = extractInvoke(stmt);
      if (invokeOpt.isPresent()) {
        int line = stmtLine(stmt);
        if (line > 0) {
          MethodSignature callSig = invokeOpt.get().getMethodSignature();
          String callTarget =
              callSig.getDeclClassType().getFullyQualifiedName() + "." + callSig.getName();
          Map<String, Object> entry = new LinkedHashMap<>();
          entry.put("line", line);
          entry.put("calls", List.of(callTarget));
          callTrace.add(entry);
        }
      }
    }
    return new CallFrame(methodClass, method.getName(), sig, minL, maxL, callTrace, List.of());
  }

  private SootMethod resolveCallee(MethodSignature sig) {
    ClassType declType = sig.getDeclClassType();
    Optional<JavaSootClass> clsOpt = view.getClass(declType);
    if (clsOpt.isEmpty()) return null;
    JavaSootClass cls = clsOpt.get();

    try {
      Optional<? extends SootMethod> mOpt = cls.getMethod(sig.getSubSignature());
      if (mOpt.isPresent() && mOpt.get().hasBody()) return mOpt.get();
    } catch (Exception ignored) {
    }

    int paramCount = sig.getParameterTypes().size();
    for (SootMethod m : cls.getMethods()) {
      if (m.getName().equals(sig.getName()) && m.getParameterCount() == paramCount && m.hasBody()) {
        return m;
      }
    }
    return null;
  }

  private List<SootMethod> findMethodsContainingLine(JavaSootClass clazz, int line) {
    List<SootMethod> result = new ArrayList<>();
    for (SootMethod method : clazz.getMethods()) {
      if (!method.hasBody()) continue;
      Body body = method.getBody();
      StmtGraph<?> graph = body.getStmtGraph();
      for (Stmt stmt : graph.getNodes()) {
        if (stmtLine(stmt) == line) {
          result.add(method);
          break;
        }
      }
    }
    return result;
  }

  private List<Stmt> stmtsAtLine(StmtGraph<?> graph, int line) {
    List<Stmt> result = new ArrayList<>();
    for (Stmt stmt : graph.getNodes()) {
      if (stmtLine(stmt) == line) {
        result.add(stmt);
      }
    }
    return result;
  }

  private List<Map<String, Object>> buildStmtDetails(List<Stmt> stmts) {
    List<Map<String, Object>> details = new ArrayList<>();
    for (Stmt stmt : stmts) {
      Map<String, Object> detail = new LinkedHashMap<>();
      detail.put("line", stmtLine(stmt));
      detail.put("jimple", stmt.toString());

      Optional<AbstractInvokeExpr> invoke = extractInvoke(stmt);
      if (invoke.isPresent()) {
        var sig = invoke.get().getMethodSignature();
        detail.put(
            "callTarget", sig.getDeclClassType().getFullyQualifiedName() + "." + sig.getName());
        detail.put("callArgCount", invoke.get().getArgCount());
      }
      if (stmt instanceof JIfStmt) {
        detail.put("branch", ((JIfStmt) stmt).getCondition().toString());
      } else if (stmt instanceof JSwitchStmt) {
        detail.put("branch", "switch");
      }
      details.add(detail);
    }
    return details;
  }

  private List<Map<String, Object>> deduplicateToSourceLines(
      List<Map<String, Object>> stmtDetails) {
    List<Map<String, Object>> result = new ArrayList<>();
    int prevLine = -2;

    for (Map<String, Object> detail : stmtDetails) {
      int line = (int) detail.get("line");
      if (line == prevLine && !result.isEmpty()) {
        Map<String, Object> prev = result.get(result.size() - 1);
        if (detail.containsKey("callTarget")) {
          @SuppressWarnings("unchecked")
          List<String> calls = (List<String>) prev.computeIfAbsent("calls", k -> new ArrayList<>());
          calls.add((String) detail.get("callTarget"));
        }
        if (detail.containsKey("branch")) {
          prev.put("branch", detail.get("branch"));
        }
      } else {
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("line", line);
        if (detail.containsKey("callTarget")) {
          List<String> calls = new ArrayList<>();
          calls.add((String) detail.get("callTarget"));
          entry.put("calls", calls);
        }
        if (detail.containsKey("branch")) {
          entry.put("branch", detail.get("branch"));
        }
        result.add(entry);
      }
      prevLine = line;
    }
    return result;
  }

  // ------------------------------------------------------------------
  // Intraprocedural tracing
  // ------------------------------------------------------------------

  private List<Stmt> backtrack(StmtGraph<?> graph, Set<Stmt> fromStmts, Set<Stmt> toStmts) {
    Map<Stmt, Stmt> parentMap = new LinkedHashMap<>();
    Queue<Stmt> queue = new ArrayDeque<>(toStmts);
    Set<Stmt> visited = new LinkedHashSet<>(toStmts);
    for (Stmt s : toStmts) {
      parentMap.put(s, null);
    }

    Set<Stmt> reachedFrom = new LinkedHashSet<>();

    while (!queue.isEmpty()) {
      Stmt current = queue.poll();
      if (fromStmts.contains(current)) {
        reachedFrom.add(current);
      }
      for (Stmt pred : graph.predecessors(current)) {
        if (visited.add(pred)) {
          parentMap.put(pred, current);
          queue.add(pred);
        }
      }
    }

    if (reachedFrom.isEmpty() && !fromStmts.isEmpty()) {
      return Collections.emptyList();
    }

    Set<Stmt> onPath = new LinkedHashSet<>();
    Queue<Stmt> traceQueue = new ArrayDeque<>(reachedFrom);
    while (!traceQueue.isEmpty()) {
      Stmt s = traceQueue.poll();
      if (onPath.add(s)) {
        Stmt next = parentMap.get(s);
        if (next != null) {
          traceQueue.add(next);
        }
      }
    }

    return new ArrayList<>(onPath);
  }

  public Map<String, Object> trace(String className, int fromLine, int toLine) {
    ClassType classType = view.getIdentifierFactory().getClassType(className);
    Optional<JavaSootClass> classOpt = view.getClass(classType);
    if (classOpt.isEmpty()) {
      throw new RuntimeException("Class not found: " + className);
    }
    JavaSootClass clazz = classOpt.get();

    List<SootMethod> candidateMethods = findMethodsContainingLine(clazz, toLine);
    if (candidateMethods.isEmpty()) {
      candidateMethods = findMethodsContainingLine(clazz, fromLine);
    }
    if (candidateMethods.isEmpty()) {
      throw new RuntimeException(
          "No method found containing line " + toLine + " or " + fromLine + " in " + className);
    }

    List<Map<String, Object>> allTraces = new ArrayList<>();

    for (SootMethod method : candidateMethods) {
      Body body = method.getBody();
      StmtGraph<?> graph = body.getStmtGraph();

      Set<Stmt> fromStmts = new LinkedHashSet<>(stmtsAtLine(graph, fromLine));
      Set<Stmt> toStmts = new LinkedHashSet<>(stmtsAtLine(graph, toLine));

      if (toStmts.isEmpty()) continue;

      List<Stmt> pathStmts;
      if (fromStmts.isEmpty()) {
        pathStmts = backtrack(graph, Collections.emptySet(), toStmts);
      } else {
        pathStmts = backtrack(graph, fromStmts, toStmts);
      }

      if (pathStmts.isEmpty() && !fromStmts.isEmpty()) continue;

      List<Map<String, Object>> stmtDetails = new ArrayList<>();
      for (Stmt stmt : pathStmts) {
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("line", stmtLine(stmt));
        detail.put("jimple", stmt.toString());

        Optional<AbstractInvokeExpr> invoke = Optional.empty();
        if (stmt instanceof JInvokeStmt) {
          invoke = ((JInvokeStmt) stmt).getInvokeExpr();
        } else if (stmt instanceof JAssignStmt) {
          invoke = ((JAssignStmt) stmt).getInvokeExpr();
        }
        if (invoke.isPresent()) {
          var sig = invoke.get().getMethodSignature();
          detail.put(
              "callTarget", sig.getDeclClassType().getFullyQualifiedName() + "." + sig.getName());
          detail.put("callArgCount", invoke.get().getArgCount());
        }

        if (stmt instanceof JIfStmt) {
          detail.put("branch", ((JIfStmt) stmt).getCondition().toString());
        } else if (stmt instanceof JSwitchStmt) {
          detail.put("branch", "switch");
        }

        stmtDetails.add(detail);
      }

      List<Map<String, Object>> sourceTrace = deduplicateToSourceLines(stmtDetails);

      Map<String, Object> methodTrace = new LinkedHashMap<>();
      methodTrace.put("method", method.getName());
      methodTrace.put("methodSignature", method.getSignature().toString());
      methodTrace.put("stmtCount", pathStmts.size());
      methodTrace.put("sourceLineCount", sourceTrace.size());
      methodTrace.put("sourceTrace", sourceTrace);
      methodTrace.put("stmtDetails", stmtDetails);
      allTraces.add(methodTrace);
    }

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("class", className);
    result.put("fromLine", fromLine);
    result.put("toLine", toLine);
    result.put("traces", allTraces);
    return result;
  }

  // ------------------------------------------------------------------
  // Dump
  // ------------------------------------------------------------------

  public Map<String, Object> dumpLineMap(String className) {
    ClassType classType = view.getIdentifierFactory().getClassType(className);
    Optional<JavaSootClass> classOpt = view.getClass(classType);
    if (classOpt.isEmpty()) {
      throw new RuntimeException("Class not found: " + className);
    }
    JavaSootClass clazz = classOpt.get();

    List<Map<String, Object>> methods = new ArrayList<>();
    for (SootMethod method : clazz.getMethods()) {
      if (!method.hasBody()) continue;
      Body body = method.getBody();
      StmtGraph<?> graph = body.getStmtGraph();

      Map<Integer, Integer> lineCounts = new TreeMap<>();
      int totalStmts = 0;
      for (Stmt stmt : graph.getNodes()) {
        int line = stmtLine(stmt);
        lineCounts.merge(line, 1, Integer::sum);
        totalStmts++;
      }

      int minLine =
          lineCounts.keySet().stream().filter(l -> l > 0).mapToInt(i -> i).min().orElse(-1);
      int maxLine = lineCounts.keySet().stream().mapToInt(i -> i).max().orElse(-1);

      Map<String, Object> m = new LinkedHashMap<>();
      m.put("method", method.getName());
      m.put("signature", method.getSignature().toString());
      m.put("lineStart", minLine);
      m.put("lineEnd", maxLine);
      m.put("stmtCount", totalStmts);
      m.put("sourceLines", lineCounts.size());
      m.put("lineMap", lineCounts);
      methods.add(m);
    }

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("class", className);
    result.put("methodCount", methods.size());
    result.put("methods", methods);
    return result;
  }
}
