package tools.bytecode;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.util.*;
import sootup.core.graph.BasicBlock;
import sootup.core.graph.StmtGraph;
import sootup.core.jimple.common.expr.AbstractInvokeExpr;
import sootup.core.jimple.common.stmt.*;
import sootup.core.jimple.javabytecode.stmt.JSwitchStmt;
import sootup.core.model.Body;
import sootup.core.model.SootMethod;
import sootup.java.core.JavaSootClass;

/**
 * Forward (top-down) call tree tracer. Starting from an entry method, DFS through all callees
 * building a recursive JSON tree with per-method block-level CFG, branch conditions, and call
 * sites.
 */
public class ForwardTracer {

  private final BytecodeTracer tracer;

  public ForwardTracer(BytecodeTracer tracer) {
    this.tracer = tracer;
  }

  public Map<String, Object> traceForward(
      String fromClass, int fromLine, BytecodeTracer.FilterConfig filter) throws IOException {
    SootMethod entryMethod = tracer.resolveMethod(fromClass, fromLine);
    String entrySig = entryMethod.getSignature().toString();

    // Index all project methods
    Map<String, SootMethod> sigToMethod = new LinkedHashMap<>();
    for (JavaSootClass cls : tracer.getProjectClasses()) {
      for (SootMethod method : cls.getMethods()) {
        if (!method.hasBody()) continue;
        sigToMethod.put(method.getSignature().toString(), method);
      }
    }
    System.err.println("Methods: " + sigToMethod.size());

    // Load call graph
    Map<String, List<String>> callerToCallees = loadForwardCallGraph();

    // DFS forward, building tree
    System.err.println("Tracing forward from " + entrySig + "...");
    int[] nodeCount = {0};
    Set<String> pathAncestors = new LinkedHashSet<>();
    Set<String> globalVisited = new HashSet<>();

    Map<String, Object> root =
        buildForwardNode(
            entrySig,
            sigToMethod,
            callerToCallees,
            filter,
            pathAncestors,
            globalVisited,
            nodeCount,
            -1);

    root.put("fromClass", fromClass);
    root.put("fromLine", fromLine);
    System.err.println("Done: " + nodeCount[0] + " nodes in tree");
    return root;
  }

  private Map<String, List<String>> loadForwardCallGraph() throws IOException {
    if (tracer.getCallGraphCache() != null && Files.exists(tracer.getCallGraphCache())) {
      System.err.println("Loading call graph from " + tracer.getCallGraphCache() + "...");
      ObjectMapper cgMapper = new ObjectMapper();
      @SuppressWarnings("unchecked")
      Map<String, List<String>> cached =
          cgMapper.readValue(tracer.getCallGraphCache().toFile(), Map.class);
      System.err.println("Loaded " + cached.size() + " caller entries");
      return cached;
    }
    throw new RuntimeException("Call graph cache not found. Run `buildcg` first.");
  }

  private Map<String, Object> buildForwardNode(
      String sig,
      Map<String, SootMethod> sigToMethod,
      Map<String, List<String>> callerToCallees,
      BytecodeTracer.FilterConfig filter,
      Set<String> pathAncestors,
      Set<String> globalVisited,
      int[] nodeCount,
      int callSiteLine) {
    Map<String, Object> node = new LinkedHashMap<>();
    nodeCount[0]++;
    if (nodeCount[0] % 100 == 0) {
      System.err.println("Nodes: " + nodeCount[0] + "...");
    }

    String className = sig.substring(1, sig.indexOf(':'));
    String methodName = sig.substring(sig.lastIndexOf(' ') + 1, sig.indexOf('('));

    if (callSiteLine > 0) node.put("callSiteLine", callSiteLine);

    // Cycle detection
    if (pathAncestors.contains(sig)) {
      node.put("class", className);
      node.put("method", methodName);
      node.put("methodSignature", sig);
      node.put("cycle", true);
      return node;
    }

    // Already expanded on a different branch
    if (globalVisited.contains(sig)) {
      node.put("class", className);
      node.put("method", methodName);
      node.put("methodSignature", sig);
      node.put("ref", true);
      return node;
    }

    SootMethod method = sigToMethod.get(sig);

    // Filtered-out or non-project method
    if (method == null || (filter != null && !filter.shouldRecurse(className))) {
      node.put("class", className);
      node.put("method", methodName);
      node.put("methodSignature", sig);
      node.put("filtered", true);
      return node;
    }

    globalVisited.add(sig);

    // Full node with sourceTrace
    BytecodeTracer.CallFrame frame = tracer.buildFrame(method, sig);
    node.put("class", frame.className());
    node.put("method", frame.methodName());
    node.put("methodSignature", sig);
    node.put("lineStart", frame.entryLine());
    node.put("lineEnd", frame.exitLine());
    node.put("sourceLineCount", frame.exitLine() - frame.entryLine() + 1);
    node.put("sourceTrace", frame.sourceTrace());
    node.put("blocks", buildBlockTrace(method));

    // Recurse into callees
    List<String> callees = callerToCallees.get(sig);
    List<Map<String, Object>> children = new ArrayList<>();
    if (callees != null) {
      pathAncestors.add(sig);
      for (String calleeSig : callees) {
        String calleeClass = calleeSig.substring(1, calleeSig.indexOf(':'));
        String calleeMethod =
            calleeSig.substring(calleeSig.lastIndexOf(' ') + 1, calleeSig.indexOf('('));
        BytecodeTracer.CallFrame calleeFrame =
            new BytecodeTracer.CallFrame(
                calleeClass, calleeMethod, calleeSig, -1, -1, List.of(), List.of());
        int csLine = BytecodeTracer.findCallSiteLine(frame, calleeFrame);

        children.add(
            buildForwardNode(
                calleeSig,
                sigToMethod,
                callerToCallees,
                filter,
                pathAncestors,
                globalVisited,
                nodeCount,
                csLine));
      }
      pathAncestors.remove(sig);
    }
    node.put("children", children);
    return node;
  }

  /** Build block-level CFG trace from a method body. */
  List<Map<String, Object>> buildBlockTrace(SootMethod method) {
    Body body = method.getBody();
    StmtGraph<?> stmtGraph = body.getStmtGraph();
    List<? extends BasicBlock<?>> blocks = stmtGraph.getBlocksSorted();
    if (blocks.isEmpty()) return List.of();

    Map<Stmt, String> stmtToBlockId = new LinkedHashMap<>();
    for (int i = 0; i < blocks.size(); i++) {
      stmtToBlockId.put(blocks.get(i).getHead(), "B" + i);
    }

    List<Map<String, Object>> blockList = new ArrayList<>();
    for (int i = 0; i < blocks.size(); i++) {
      BasicBlock<?> block = blocks.get(i);
      Map<String, Object> blockMap = new LinkedHashMap<>();
      blockMap.put("id", "B" + i);

      List<Map<String, Object>> stmtList = new ArrayList<>();
      for (Stmt stmt : block.getStmts()) {
        Map<String, Object> s = new LinkedHashMap<>();
        int line = BytecodeTracer.stmtLine(stmt);
        s.put("line", line);

        Optional<AbstractInvokeExpr> invoke = BytecodeTracer.extractInvoke(stmt);
        if (invoke.isPresent()) {
          var msig = invoke.get().getMethodSignature();
          s.put("call", msig.getDeclClassType().getFullyQualifiedName() + "." + msig.getName());
        } else if (stmt instanceof JAssignStmt assign) {
          String rhs = assign.getRightOp().toString();
          String lhs = assign.getLeftOp().toString();
          if (!rhs.contains("$stack") && !rhs.contains(".<") && !lhs.startsWith("$stack")) {
            s.put("assign", lhs + " = " + rhs);
          }
        }
        if (stmt instanceof JIfStmt) {
          s.put("branch", ((JIfStmt) stmt).getCondition().toString());
        } else if (stmt instanceof JSwitchStmt) {
          s.put("branch", "switch");
        }
        stmtList.add(s);
      }
      blockMap.put("stmts", stmtList);

      List<String> successorIds = new ArrayList<>();
      for (BasicBlock<?> succ : block.getSuccessors()) {
        String succId = stmtToBlockId.get(succ.getHead());
        if (succId != null) {
          successorIds.add(succId);
        }
      }
      blockMap.put("successors", successorIds);

      // Branch condition from tail statement
      Stmt tail = block.getTail();
      if (tail instanceof JIfStmt) {
        String cond = ((JIfStmt) tail).getCondition().toString();
        for (Stmt s : block.getStmts()) {
          if (s instanceof JAssignStmt assign) {
            String lhs = assign.getLeftOp().toString();
            if (lhs.startsWith("$stack") && cond.contains(lhs)) {
              Optional<AbstractInvokeExpr> inv = assign.getInvokeExpr();
              if (inv.isPresent()) {
                var msig = inv.get().getMethodSignature();
                String shortCall =
                    msig.getDeclClassType().getClassName() + "." + msig.getName() + "()";
                boolean isBool = msig.getType().toString().equals("boolean");
                cond = cond.replace(lhs, shortCall);
                if (isBool) {
                  cond =
                      cond.replace(shortCall + " == 0", shortCall + " == false")
                          .replace(shortCall + " != 0", shortCall + " == true");
                }
              } else {
                String rhs = assign.getRightOp().toString();
                cond = cond.replace(lhs, rhs);
              }
            }
          }
        }
        blockMap.put("branchCondition", cond);
      } else if (tail instanceof JSwitchStmt) {
        blockMap.put("branchCondition", "switch");
      }

      blockList.add(blockMap);
    }
    return blockList;
  }
}
