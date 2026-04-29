package tools.bytecode;

import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import sootup.core.jimple.common.expr.AbstractInvokeExpr;
import sootup.core.jimple.common.expr.JSpecialInvokeExpr;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.Body;
import sootup.core.model.MethodModifier;
import sootup.core.model.SootMethod;
import sootup.core.signatures.MethodSignature;
import sootup.core.types.ClassType;
import sootup.java.core.JavaSootClass;

/**
 * Builds a whole-program call graph from compiled .class files. Scans all project classes, extracts
 * invoke stmts, records caller→callee edges, and resolves polymorphic dispatch
 * (interface→implementation).
 *
 * <p>Phases 1 and 2 run concurrently via CompletableFuture. Phase 3 uses parallelStream over
 * classes. Phase 1 pre-warms SootUp's lazy body cache so Phase 3's concurrent reads are safe.
 */
public class CallGraphBuilder {

  private final BytecodeTracer tracer;

  public CallGraphBuilder(BytecodeTracer tracer) {
    this.tracer = tracer;
  }

  private record IndexResult(
      Map<String, String> sigIndex,
      Map<String, List<String>> nameIndex,
      Set<String> bridgeSigs,
      int methodsWithBodies) {}

  public Map<String, List<String>> buildCallGraph() {
    long totalStart = System.currentTimeMillis();

    System.err.println("[buildcg] Loading project classes...");
    List<JavaSootClass> projectClasses = tracer.getProjectClasses();
    System.err.printf("[buildcg] Loaded %d classes.%n", projectClasses.size());

    System.err.println("[Phase 1+2] Indexing methods and building dispatch map (concurrent)...");
    long phase12Start = System.currentTimeMillis();
    CompletableFuture<IndexResult> indexFuture =
        CompletableFuture.supplyAsync(() -> buildMethodIndex(projectClasses));
    CompletableFuture<Map<String, List<String>>> ifaceFuture =
        CompletableFuture.supplyAsync(() -> buildIfaceMap(projectClasses));
    CompletableFuture.allOf(indexFuture, ifaceFuture).join();
    IndexResult index = indexFuture.join();
    Map<String, List<String>> ifaceToImpls = ifaceFuture.join();
    System.err.printf(
        "[Phase 1] %d methods indexed, %d bridge sigs.%n",
        index.sigIndex().size(), index.bridgeSigs().size());
    System.err.printf("[Phase 2] %d interface→impl mappings.%n", ifaceToImpls.size());
    System.err.printf(
        "[Phase 1+2] Done in %.1fs.%n", (System.currentTimeMillis() - phase12Start) / 1000.0);

    int totalClasses = projectClasses.size();
    System.err.printf(
        "[Phase 3] Scanning %d classes (%d methods with bodies, parallelStream)...%n",
        totalClasses, index.methodsWithBodies());
    long phase3Start = System.currentTimeMillis();
    Map<String, Set<String>> callerToCallees = new ConcurrentHashMap<>();
    AtomicInteger classesScanned = new AtomicInteger(0);

    projectClasses.parallelStream()
        .forEach(
            cls -> {
              for (SootMethod method : cls.getMethods()) {
                if (!method.hasBody()) continue;
                String mSig = method.getSignature().toString();
                Body body = method.getBody();
                for (Stmt stmt : body.getStmtGraph().getNodes()) {
                  Optional<AbstractInvokeExpr> invokeOpt = BytecodeTracer.extractInvoke(stmt);
                  if (invokeOpt.isEmpty()) continue;
                  AbstractInvokeExpr invoke = invokeOpt.get();
                  if (invoke instanceof JSpecialInvokeExpr) continue;
                  MethodSignature callSig = invoke.getMethodSignature();
                  String declClass = callSig.getDeclClassType().getFullyQualifiedName();
                  String methodName = callSig.getName();
                  int paramCount = callSig.getParameterTypes().size();
                  Set<String> targetClasses = new LinkedHashSet<>();
                  targetClasses.add(declClass);
                  List<String> impls = ifaceToImpls.get(declClass);
                  if (impls != null) targetClasses.addAll(impls);
                  for (String targetClass : targetClasses) {
                    String key = targetClass + "#" + methodName + "#" + paramCount;
                    List<String> candidates = index.nameIndex().get(key);
                    if (candidates != null) {
                      callerToCallees
                          .computeIfAbsent(mSig, k -> ConcurrentHashMap.newKeySet())
                          .addAll(candidates);
                    }
                  }
                }
              }
              logPhase3Progress(classesScanned.incrementAndGet(), totalClasses, phase3Start);
            });

    int totalEdgesFound = callerToCallees.values().stream().mapToInt(Set::size).sum();
    System.err.printf(
        "[Phase 3] Done in %.1fs. %d callers, %d call edges found.%n",
        (System.currentTimeMillis() - phase3Start) / 1000.0,
        callerToCallees.size(),
        totalEdgesFound);

    // Convert sets to lists for JSON serialization
    Map<String, List<String>> raw = new LinkedHashMap<>();
    for (var entry : callerToCallees.entrySet()) {
      raw.put(entry.getKey(), new ArrayList<>(entry.getValue()));
    }

    System.err.printf("[Phase 4] Collapsing %d bridge method(s)...%n", index.bridgeSigs().size());
    Map<String, List<String>> result = collapseBridgeMethods(raw, index.bridgeSigs());
    int edges = result.values().stream().mapToInt(List::size).sum();
    System.err.printf(
        "[buildcg] Complete: %d callers, %d edges. Total: %.1fs.%n",
        result.size(), edges, (System.currentTimeMillis() - totalStart) / 1000.0);
    return result;
  }

  /**
   * Phase 1: Iterates all class methods to build the signature index and name lookup map. Also
   * pre-warms SootUp's lazy body cache by calling {@code method.getBody()} for every method that
   * has a body, so that Phase 3's {@code parallelStream} reads from a stable, fully-populated
   * cache.
   */
  private IndexResult buildMethodIndex(List<JavaSootClass> classes) {
    Map<String, String> sigIndex = new LinkedHashMap<>();
    Map<String, List<String>> nameIndex = new LinkedHashMap<>();
    Set<String> bridgeSigs = new LinkedHashSet<>();
    int bodiesLoaded = 0;
    for (JavaSootClass cls : classes) {
      String clsName = cls.getType().getFullyQualifiedName();
      for (SootMethod method : cls.getMethods()) {
        if (!method.hasBody()) continue;
        method.getBody(); // pre-warm SootUp's lazy cache so Phase 3 parallelStream is safe
        String sig = method.getSignature().toString();
        sigIndex.put(sig, sig);
        String key = clsName + "#" + method.getName() + "#" + method.getParameterCount();
        nameIndex.computeIfAbsent(key, k -> new ArrayList<>()).add(sig);
        if (MethodModifier.isBridge(method.getModifiers())) {
          bridgeSigs.add(sig);
        }
        bodiesLoaded++;
      }
    }
    return new IndexResult(sigIndex, nameIndex, bridgeSigs, bodiesLoaded);
  }

  /**
   * Phase 2: Builds the interface→implementation and superclass→subclass maps for polymorphic
   * dispatch resolution.
   */
  private Map<String, List<String>> buildIfaceMap(List<JavaSootClass> classes) {
    Map<String, List<String>> ifaceToImpls = new LinkedHashMap<>();
    for (JavaSootClass cls : classes) {
      if (cls.isInterface()) continue;
      String clsName = cls.getType().getFullyQualifiedName();
      for (ClassType iface : cls.getInterfaces()) {
        ifaceToImpls
            .computeIfAbsent(iface.getFullyQualifiedName(), k -> new ArrayList<>())
            .add(clsName);
      }
      cls.getSuperclass()
          .map(ClassType::getFullyQualifiedName)
          .filter(name -> !name.equals("java.lang.Object"))
          .ifPresent(
              name -> ifaceToImpls.computeIfAbsent(name, k -> new ArrayList<>()).add(clsName));
    }
    return ifaceToImpls;
  }

  private static void logPhase3Progress(int done, int total, long startMs) {
    if (done % 50 != 0 && done != total) return;
    long elapsed = System.currentTimeMillis() - startMs;
    int pct = done * 100 / total;
    if (done < total) {
      long remaining = elapsed * (total - done) / done;
      System.err.printf(
          "[Phase 3]  %d/%d classes (%d%%) — %.1fs elapsed, ~%.1fs remaining%n",
          done, total, pct, elapsed / 1000.0, remaining / 1000.0);
    } else {
      System.err.printf("[Phase 3]  %d/%d — done in %.1fs.%n", done, total, elapsed / 1000.0);
    }
  }

  /**
   * Removes compiler-generated bridge methods from the call graph and redirects their callers to
   * the real target methods. Bridge sigs are identified by the caller (via {@code ACC_BRIDGE}).
   *
   * <p>For each bridge {@code B}: every entry whose callee list contains {@code B} has {@code B}
   * replaced by {@code B}'s own callees (excluding any self-loop on {@code B}). {@code B}'s entry
   * is then removed. Duplicate callee refs introduced by the redirect are deduplicated.
   *
   * @param graph raw call graph (caller → callees)
   * @param bridgeSigs signatures of all bridge methods detected during class scanning
   * @return new graph with bridge entries removed and callers redirected
   */
  static Map<String, List<String>> collapseBridgeMethods(
      Map<String, List<String>> graph, Set<String> bridgeSigs) {
    if (bridgeSigs.isEmpty()) return graph;

    Map<String, List<String>> result = new LinkedHashMap<>();
    for (var entry : graph.entrySet()) {
      if (bridgeSigs.contains(entry.getKey())) continue;

      List<String> redirected =
          entry.getValue().stream()
              .flatMap(
                  callee ->
                      bridgeSigs.contains(callee)
                          ? graph.getOrDefault(callee, List.of()).stream()
                              .filter(c -> !c.equals(callee)) // drop self-loop
                          : java.util.stream.Stream.of(callee))
              .distinct()
              .collect(Collectors.toList());

      result.put(entry.getKey(), redirected);
    }

    System.err.println("Collapsed " + bridgeSigs.size() + " bridge method(s).");
    return result;
  }
}
