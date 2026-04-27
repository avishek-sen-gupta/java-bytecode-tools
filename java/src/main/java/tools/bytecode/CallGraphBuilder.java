package tools.bytecode;

import java.util.*;
import sootup.core.jimple.common.expr.AbstractInvokeExpr;
import sootup.core.jimple.common.expr.JSpecialInvokeExpr;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.Body;
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

    int indexed = 0;
    for (JavaSootClass cls : projectClasses) {
      String clsName = cls.getType().getFullyQualifiedName();
      for (SootMethod method : cls.getMethods()) {
        if (!method.hasBody()) continue;
        String sig = method.getSignature().toString();
        sigIndex.put(sig, sig);
        String key = clsName + "#" + method.getName() + "#" + method.getParameterCount();
        nameIndex.computeIfAbsent(key, k -> new ArrayList<>()).add(sig);
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
    Map<String, List<String>> result = new LinkedHashMap<>();
    for (var entry : callerToCallees.entrySet()) {
      result.put(entry.getKey(), new ArrayList<>(entry.getValue()));
    }

    int edges = result.values().stream().mapToInt(List::size).sum();
    System.err.println("Done. " + result.size() + " callers, " + edges + " edges.");
    return result;
  }
}
