package tools.bytecode;

import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
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

  private static final Logger log = LoggerFactory.getLogger(CallGraphBuilder.class);

  private final BytecodeTracer tracer;
  private final StmtAnalyzer stmtAnalyzer;

  public CallGraphBuilder(BytecodeTracer tracer) {
    this.tracer = tracer;
    this.stmtAnalyzer = tracer != null ? tracer.getStmtAnalyzer() : new StmtAnalyzer();
  }

  private record IndexResult(
      Map<String, String> sigIndex,
      Map<String, List<String>> nameIndex,
      Set<String> bridgeSigs,
      int methodsWithBodies,
      Map<String, MethodLineRange> methodLines) {}

  public record MethodLineRange(int lineStart, int lineEnd) {}

  public record CallGraphResult(
      Map<String, List<String>> graph,
      Map<String, Map<String, Integer>> callsites,
      Map<String, MethodLineRange> methodLines) {}

  public CallGraphResult buildCallGraph() {
    long totalStart = System.currentTimeMillis();

    log.info("[buildcg] Loading project classes...");
    List<JavaSootClass> projectClasses = tracer.getProjectClasses();
    log.info("[buildcg] Loaded {} classes.", projectClasses.size());

    log.info("[Phase 1+2] Indexing methods and building dispatch map (concurrent)...");
    long phase12Start = System.currentTimeMillis();
    CompletableFuture<IndexResult> indexFuture =
        CompletableFuture.supplyAsync(() -> buildMethodIndex(projectClasses));
    CompletableFuture<Map<String, List<String>>> ifaceFuture =
        CompletableFuture.supplyAsync(() -> buildIfaceMap(projectClasses));
    CompletableFuture.allOf(indexFuture, ifaceFuture).join();
    IndexResult index = indexFuture.join();
    Map<String, List<String>> ifaceToImpls = ifaceFuture.join();
    log.info(
        "[Phase 1] {} methods indexed, {} bridge sigs.",
        index.sigIndex().size(),
        index.bridgeSigs().size());
    log.info("[Phase 2] {} interface\u2192impl mappings.", ifaceToImpls.size());
    log.info("[Phase 1+2] Done in {}", elapsedSecs(phase12Start));

    int totalClasses = projectClasses.size();
    int totalMethods = index.methodsWithBodies();
    log.info(
        "[Phase 3] Scanning {} classes / {} methods (sequential)...", totalClasses, totalMethods);
    long phase3Start = System.currentTimeMillis();
    Map<String, Set<String>> callerToCallees = new ConcurrentHashMap<>();
    Map<String, Map<String, Integer>> rawCallsites = new ConcurrentHashMap<>();
    AtomicInteger classesScanned = new AtomicInteger(0);
    AtomicInteger methodsScanned = new AtomicInteger(0);

    ScheduledExecutorService ticker = Executors.newSingleThreadScheduledExecutor();
    ticker.scheduleAtFixedRate(
        () -> {
          int mDone = methodsScanned.get();
          int cDone = classesScanned.get();
          int mPct = totalMethods > 0 ? mDone * 100 / totalMethods : 0;
          long elapsed = System.currentTimeMillis() - phase3Start;
          String eta =
              (mDone > 0 && mDone < totalMethods)
                  ? String.format(
                      "~%.1fs remaining", elapsed * (totalMethods - mDone) / (1000.0 * mDone))
                  : "";
          log.info(
              "[Phase 3]  {}/{} methods ({}%) | {}/{} classes | {}s elapsed {}",
              mDone,
              totalMethods,
              mPct,
              cDone,
              totalClasses,
              String.format("%.1f", elapsed / 1000.0),
              eta);
        },
        1,
        1,
        TimeUnit.SECONDS);

    try {
      for (JavaSootClass cls : projectClasses) {
        for (SootMethod method : cls.getMethods()) {
          if (!method.hasBody()) continue;
          String mSig = method.getSignature().toString();
          Body body = method.getBody();
          for (Stmt stmt : body.getStmtGraph().getNodes()) {
            Optional<AbstractInvokeExpr> invokeOpt = stmtAnalyzer.extractInvoke(stmt);
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
            int callLine = stmtAnalyzer.stmtLine(stmt);
            for (String targetClass : targetClasses) {
              String key = targetClass + "#" + methodName + "#" + paramCount;
              List<String> candidates = index.nameIndex().get(key);
              if (candidates != null) {
                callerToCallees
                    .computeIfAbsent(mSig, k -> ConcurrentHashMap.newKeySet())
                    .addAll(candidates);
                if (callLine > 0) {
                  Map<String, Integer> siteMap =
                      rawCallsites.computeIfAbsent(mSig, k -> new ConcurrentHashMap<>());
                  for (String cSig : candidates) {
                    siteMap.putIfAbsent(cSig, callLine);
                  }
                }
              }
            }
            methodsScanned.incrementAndGet();
          }
        }
        classesScanned.incrementAndGet();
      }
    } finally {
      ticker.shutdown();
    }

    int totalEdgesFound = callerToCallees.values().stream().mapToInt(Set::size).sum();
    log.info(
        "[Phase 3] Done in {}. {} callers, {} call edges found.",
        elapsedSecs(phase3Start),
        callerToCallees.size(),
        totalEdgesFound);

    // Convert sets to lists for JSON serialization
    Map<String, List<String>> raw = new LinkedHashMap<>();
    for (var entry : callerToCallees.entrySet()) {
      raw.put(entry.getKey(), new ArrayList<>(entry.getValue()));
    }

    log.info("[Phase 4] Collapsing {} bridge method(s)...", index.bridgeSigs().size());
    Map<String, List<String>> result = collapseBridgeMethods(raw, index.bridgeSigs());
    Map<String, Map<String, Integer>> callsites =
        collapseCallsiteBridges(rawCallsites, index.bridgeSigs(), raw);
    int edges = result.values().stream().mapToInt(List::size).sum();
    log.info(
        "[buildcg] Complete: {} callers, {} edges. Total: {}",
        result.size(),
        edges,
        elapsedSecs(totalStart));
    return new CallGraphResult(
        result,
        Collections.unmodifiableMap(callsites),
        Collections.unmodifiableMap(index.methodLines()));
  }

  /** Phase 1: Iterates all class methods to build the signature index and name lookup map. */
  private IndexResult buildMethodIndex(List<JavaSootClass> classes) {
    Map<String, String> sigIndex = new LinkedHashMap<>();
    Map<String, List<String>> nameIndex = new LinkedHashMap<>();
    Set<String> bridgeSigs = new LinkedHashSet<>();
    Map<String, MethodLineRange> methodLines = new LinkedHashMap<>();
    int total = classes.size();
    long startMs = System.currentTimeMillis();
    AtomicInteger classesIndexed = new AtomicInteger(0);
    AtomicInteger methodsIndexed = new AtomicInteger(0);

    ScheduledExecutorService ticker = Executors.newSingleThreadScheduledExecutor();
    ticker.scheduleAtFixedRate(
        () -> {
          int cDone = classesIndexed.get();
          int mDone = methodsIndexed.get();
          int pct = cDone * 100 / total;
          long elapsed = System.currentTimeMillis() - startMs;
          String eta =
              (cDone > 0 && cDone < total)
                  ? String.format("~%.1fs remaining", elapsed * (total - cDone) / (1000.0 * cDone))
                  : "";
          log.info(
              "[Phase 1]  {}/{} classes ({}%) | {} methods indexed | {}s elapsed {}",
              cDone, total, pct, mDone, String.format("%.1f", elapsed / 1000.0), eta);
        },
        1,
        1,
        TimeUnit.SECONDS);

    try {
      for (JavaSootClass cls : classes) {
        String clsName = cls.getType().getFullyQualifiedName();
        for (SootMethod method : cls.getMethods()) {
          if (!method.hasBody()) continue;
          Body body = method.getBody(); // pre-warm SootUp's lazy body cache
          String sig = method.getSignature().toString();
          sigIndex.put(sig, sig);
          String key = clsName + "#" + method.getName() + "#" + method.getParameterCount();
          nameIndex.computeIfAbsent(key, k -> new ArrayList<>()).add(sig);
          if (MethodModifier.isBridge(method.getModifiers())) {
            bridgeSigs.add(sig);
          }
          List<sootup.core.jimple.common.stmt.Stmt> stmts =
              new java.util.ArrayList<>(body.getStmtGraph().getNodes());
          int minL =
              stmts.stream().mapToInt(stmtAnalyzer::stmtLine).filter(l -> l > 0).min().orElse(-1);
          int maxL = stmts.stream().mapToInt(stmtAnalyzer::stmtLine).max().orElse(-1);
          if (minL > 0 && maxL > 0) {
            methodLines.put(sig, new MethodLineRange(minL, maxL));
          }
          methodsIndexed.incrementAndGet();
        }
        classesIndexed.incrementAndGet();
      }
    } finally {
      ticker.shutdown();
    }
    return new IndexResult(sigIndex, nameIndex, bridgeSigs, methodsIndexed.get(), methodLines);
  }

  /**
   * Phase 2: Builds the interface→implementation and superclass→subclass maps for polymorphic
   * dispatch resolution.
   */
  private Map<String, List<String>> buildIfaceMap(List<JavaSootClass> classes) {
    Map<String, List<String>> ifaceToImpls = new LinkedHashMap<>();
    int total = classes.size();
    long startMs = System.currentTimeMillis();
    AtomicInteger classesScanned = new AtomicInteger(0);
    AtomicInteger mappingsFound = new AtomicInteger(0);

    ScheduledExecutorService ticker = Executors.newSingleThreadScheduledExecutor();
    ticker.scheduleAtFixedRate(
        () -> {
          int cDone = classesScanned.get();
          int pct = cDone * 100 / total;
          long elapsed = System.currentTimeMillis() - startMs;
          String eta =
              (cDone > 0 && cDone < total)
                  ? String.format("~%.1fs remaining", elapsed * (total - cDone) / (1000.0 * cDone))
                  : "";
          log.info(
              "[Phase 2]  {}/{} classes ({}%) | {} mappings | {}s elapsed {}",
              cDone, total, pct, mappingsFound.get(), String.format("%.1f", elapsed / 1000.0), eta);
        },
        1,
        1,
        TimeUnit.SECONDS);

    try {
      for (JavaSootClass cls : classes) {
        if (cls.isInterface()) {
          classesScanned.incrementAndGet();
          continue;
        }
        String clsName = cls.getType().getFullyQualifiedName();
        for (ClassType iface : cls.getInterfaces()) {
          ifaceToImpls
              .computeIfAbsent(iface.getFullyQualifiedName(), k -> new ArrayList<>())
              .add(clsName);
          mappingsFound.incrementAndGet();
        }
        cls.getSuperclass()
            .map(ClassType::getFullyQualifiedName)
            .filter(name -> !name.equals("java.lang.Object"))
            .ifPresent(
                name -> {
                  ifaceToImpls.computeIfAbsent(name, k -> new ArrayList<>()).add(clsName);
                  mappingsFound.incrementAndGet();
                });
        classesScanned.incrementAndGet();
      }
    } finally {
      ticker.shutdown();
    }
    return ifaceToImpls;
  }

  private String elapsedSecs(long startMs) {
    return String.format("%.1fs", (System.currentTimeMillis() - startMs) / 1000.0);
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
  Map<String, List<String>> collapseBridgeMethods(
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

    log.info("Collapsed {} bridge method(s).", bridgeSigs.size());
    return result;
  }

  /**
   * Redirects callsite entries whose callee is a bridge method to the real target(s), preserving
   * the original callsite line number. Bridge caller entries are removed.
   */
  Map<String, Map<String, Integer>> collapseCallsiteBridges(
      Map<String, Map<String, Integer>> callsites,
      Set<String> bridgeSigs,
      Map<String, List<String>> rawGraph) {
    if (bridgeSigs.isEmpty()) return callsites;
    Map<String, Map<String, Integer>> result = new LinkedHashMap<>();
    for (var outer : callsites.entrySet()) {
      String callerSig = outer.getKey();
      if (bridgeSigs.contains(callerSig)) continue;
      Map<String, Integer> redirected = new LinkedHashMap<>();
      for (var inner : outer.getValue().entrySet()) {
        String calleeSig = inner.getKey();
        int line = inner.getValue();
        if (bridgeSigs.contains(calleeSig)) {
          for (String real : rawGraph.getOrDefault(calleeSig, List.of())) {
            if (!real.equals(calleeSig)) redirected.putIfAbsent(real, line);
          }
        } else {
          redirected.putIfAbsent(calleeSig, line);
        }
      }
      if (!redirected.isEmpty()) result.put(callerSig, redirected);
    }
    return result;
  }
}
