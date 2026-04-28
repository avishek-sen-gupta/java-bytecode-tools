package tools.bytecode;

import java.util.*;
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
 */
public class CallGraphBuilder {

  private final BytecodeTracer tracer;

  public CallGraphBuilder(BytecodeTracer tracer) {
    this.tracer = tracer;
  }

  public Map<String, List<String>> buildCallGraph() {
    System.err.println("Building call graph...");
    List<JavaSootClass> projectClasses = tracer.getProjectClasses();
    System.err.println("Loaded " + projectClasses.size() + " project classes.");

    // Index method sigs for resolution
    Map<String, String> sigIndex = new LinkedHashMap<>();
    Map<String, List<String>> nameIndex = new LinkedHashMap<>();

    Set<String> bridgeSigs = new LinkedHashSet<>();
    int indexed = 0;
    for (JavaSootClass cls : projectClasses) {
      String clsName = cls.getType().getFullyQualifiedName();
      for (SootMethod method : cls.getMethods()) {
        if (!method.hasBody()) continue;
        String sig = method.getSignature().toString();
        sigIndex.put(sig, sig);
        String key = clsName + "#" + method.getName() + "#" + method.getParameterCount();
        nameIndex.computeIfAbsent(key, k -> new ArrayList<>()).add(sig);
        if (MethodModifier.isBridge(method.getModifiers())) {
          bridgeSigs.add(sig);
        }
        indexed++;
        if (indexed % 1000 == 0) System.err.println("  indexed " + indexed + " methods...");
      }
    }
    System.err.println("Indexed " + sigIndex.size() + " methods.");

    // Build interface → implementation map for polymorphic dispatch resolution
    Map<String, List<String>> ifaceToImpls = new LinkedHashMap<>();
    for (JavaSootClass cls : projectClasses) {
      if (cls.isInterface()) continue;
      String clsName = cls.getType().getFullyQualifiedName();
      for (ClassType iface : cls.getInterfaces()) {
        String ifaceName = iface.getFullyQualifiedName();
        ifaceToImpls.computeIfAbsent(ifaceName, k -> new ArrayList<>()).add(clsName);
      }
      var superOpt = cls.getSuperclass();
      if (superOpt.isPresent()) {
        String superName = superOpt.get().getFullyQualifiedName();
        if (!superName.equals("java.lang.Object")) {
          ifaceToImpls.computeIfAbsent(superName, k -> new ArrayList<>()).add(clsName);
        }
      }
    }
    System.err.println("Built " + ifaceToImpls.size() + " interface→impl mappings.");

    // Scan all method bodies for call edges
    Map<String, Set<String>> callerToCallees = new LinkedHashMap<>();
    int scanned = 0;
    for (JavaSootClass cls : projectClasses) {
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
            List<String> candidates = nameIndex.get(key);
            if (candidates != null) {
              for (String calleeSig : candidates) {
                callerToCallees.computeIfAbsent(mSig, k -> new LinkedHashSet<>()).add(calleeSig);
              }
            }
          }
        }
        scanned++;
        if (scanned % 1000 == 0) System.err.println("  scanned " + scanned + " methods...");
      }
    }

    // Convert sets to lists for JSON
    Map<String, List<String>> raw = new LinkedHashMap<>();
    for (var entry : callerToCallees.entrySet()) {
      raw.put(entry.getKey(), new ArrayList<>(entry.getValue()));
    }

    Map<String, List<String>> result = collapseBridgeMethods(raw, bridgeSigs);
    int edges = result.values().stream().mapToInt(List::size).sum();
    System.err.println("Done. " + result.size() + " callers, " + edges + " edges.");
    return result;
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
