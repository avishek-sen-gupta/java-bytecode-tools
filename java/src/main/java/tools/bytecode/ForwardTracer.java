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

  // JSON field name constants
  static final String F_CLASS = "class";
  static final String F_METHOD = "method";
  static final String F_METHOD_SIGNATURE = "methodSignature";
  static final String F_CALL_SITE_LINE = "callSiteLine";
  static final String F_REF = "ref";
  static final String F_CYCLE = "cycle";
  static final String F_FILTERED = "filtered";
  static final String F_LINE_START = "lineStart";
  static final String F_LINE_END = "lineEnd";
  static final String F_SOURCE_LINE_COUNT = "sourceLineCount";
  static final String F_SOURCE_TRACE = "sourceTrace";
  static final String F_BLOCKS = "blocks";
  static final String F_EDGES = "edges";
  static final String F_TRAPS = "traps";
  static final String F_CHILDREN = "children";
  static final String F_FROM_CLASS = "fromClass";
  static final String F_FROM_LINE = "fromLine";
  static final String F_TRACE = "trace";
  static final String F_REF_INDEX = "refIndex";

  /**
   * Extract the fully qualified class name from a SootUp signature like {@code <com.example.Foo:
   * void bar(int)>}.
   */
  static String extractClassName(String sig) {
    return sig.substring(1, sig.indexOf(':'));
  }

  /**
   * Extract the method name from a SootUp signature like {@code <com.example.Foo: void bar(int)>}.
   */
  static String extractMethodName(String sig) {
    return sig.substring(sig.lastIndexOf(' ') + 1, sig.indexOf('('));
  }

  /**
   * Pass 1 — Discover all reachable methods from a root signature via DFS over the call graph.
   *
   * <p>Pure function over the call graph — no SootUp access. Testable with synthetic graphs.
   *
   * @param rootSig entry method signature
   * @param callGraph prebuilt caller→callees map
   * @param knownSignatures set of signatures that have bodies (project methods)
   * @param filter class-level allow/stop filter (null-safe)
   * @return discovery result with classifications and callee lists
   */
  static DiscoveryResult discoverReachable(
      String rootSig,
      Map<String, List<String>> callGraph,
      Set<String> knownSignatures,
      BytecodeTracer.FilterConfig filter) {
    Set<String> normalMethods = new LinkedHashSet<>();
    Map<String, List<DiscoveryResult.CalleeEntry>> calleeMap = new LinkedHashMap<>();
    Set<String> pathAncestors = new LinkedHashSet<>();
    Set<String> visited = new HashSet<>();

    discoverDFS(
        rootSig,
        callGraph,
        knownSignatures,
        filter,
        pathAncestors,
        visited,
        normalMethods,
        calleeMap);

    return new DiscoveryResult(normalMethods, calleeMap);
  }

  private static void discoverDFS(
      String sig,
      Map<String, List<String>> callGraph,
      Set<String> knownSignatures,
      BytecodeTracer.FilterConfig filter,
      Set<String> pathAncestors,
      Set<String> visited,
      Set<String> normalMethods,
      Map<String, List<DiscoveryResult.CalleeEntry>> calleeMap) {
    if (visited.contains(sig)) return;
    visited.add(sig);

    normalMethods.add(sig);
    pathAncestors.add(sig);

    List<String> callees = callGraph.getOrDefault(sig, List.of());
    List<DiscoveryResult.CalleeEntry> entries = new ArrayList<>();
    for (String calleeSig : callees) {
      Classification classification =
          classifyCallee(calleeSig, pathAncestors, knownSignatures, filter);
      entries.add(new DiscoveryResult.CalleeEntry(calleeSig, classification));
      if (classification == Classification.NORMAL) {
        discoverDFS(
            calleeSig,
            callGraph,
            knownSignatures,
            filter,
            pathAncestors,
            visited,
            normalMethods,
            calleeMap);
      }
    }

    pathAncestors.remove(sig);
    calleeMap.put(sig, List.copyOf(entries));
  }

  private static Classification classifyCallee(
      String calleeSig,
      Set<String> pathAncestors,
      Set<String> knownSignatures,
      BytecodeTracer.FilterConfig filter) {
    if (pathAncestors.contains(calleeSig)) return Classification.CYCLE;
    if (!knownSignatures.contains(calleeSig)) return Classification.FILTERED;
    if (filter != null && filter.stop() != null) {
      String calleeClass = extractClassName(calleeSig);
      if (!filter.shouldRecurse(calleeClass)) return Classification.FILTERED;
    }
    return Classification.NORMAL;
  }

  /**
   * Build a child node for a callee. Always produces a leaf (ref, cycle, or filtered).
   *
   * @param calleeSig callee method signature
   * @param classification how this callee was classified during discovery
   * @param callSiteLine source line of the call site (omitted if <= 0)
   * @return map suitable for inclusion in the "children" list
   */
  static Map<String, Object> buildChildNode(
      String calleeSig, Classification classification, int callSiteLine) {
    Map<String, Object> node = new LinkedHashMap<>();
    node.put(F_CLASS, extractClassName(calleeSig));
    node.put(F_METHOD, extractMethodName(calleeSig));
    node.put(F_METHOD_SIGNATURE, calleeSig);

    if (callSiteLine > 0) {
      node.put(F_CALL_SITE_LINE, callSiteLine);
    }

    switch (classification) {
      case NORMAL -> node.put(F_REF, true);
      case CYCLE -> node.put(F_CYCLE, true);
      case FILTERED -> node.put(F_FILTERED, true);
    }

    return node;
  }

  /**
   * Resolve the source line where a caller invokes a callee. Builds a lightweight CallFrame for the
   * callee (no body needed) and delegates to {@link BytecodeTracer#findCallSiteLine}.
   */
  private static int resolveCallSiteLine(BytecodeTracer.CallFrame callerFrame, String calleeSig) {
    String calleeClass = extractClassName(calleeSig);
    String calleeMethod = extractMethodName(calleeSig);
    BytecodeTracer.CallFrame calleeFrame =
        new BytecodeTracer.CallFrame(
            calleeClass, calleeMethod, calleeSig, -1, -1, List.of(), List.of());
    return BytecodeTracer.findCallSiteLine(callerFrame, calleeFrame);
  }

  /**
   * Pass 2 — Build a single method's CFG with ref children.
   *
   * <p>No recursion. Each callee becomes a ref/cycle/filtered leaf via {@link #buildChildNode}.
   * Called in a flat loop for all discovered methods.
   */
  private Map<String, Object> buildMethodCFG(
      String sig, Map<String, SootMethod> sigToMethod, DiscoveryResult discovery) {
    SootMethod method = sigToMethod.get(sig);
    BytecodeTracer.CallFrame frame = tracer.buildFrame(method, sig);

    Map<String, Object> node = new LinkedHashMap<>();
    node.put(F_CLASS, frame.className());
    node.put(F_METHOD, frame.methodName());
    node.put(F_METHOD_SIGNATURE, sig);
    node.put(F_LINE_START, frame.entryLine());
    node.put(F_LINE_END, frame.exitLine());
    node.put(F_SOURCE_LINE_COUNT, frame.exitLine() - frame.entryLine() + 1);
    node.put(F_SOURCE_TRACE, frame.sourceTrace());

    Map<String, Object> blockInfo = buildBlockTrace(method);
    node.put(F_BLOCKS, blockInfo.get("blocks"));
    node.put(F_EDGES, blockInfo.get("edges"));
    node.put(F_TRAPS, blockInfo.get("traps"));

    List<DiscoveryResult.CalleeEntry> callees = discovery.calleeMap().getOrDefault(sig, List.of());
    List<Map<String, Object>> children = new ArrayList<>();
    for (DiscoveryResult.CalleeEntry entry : callees) {
      int csLine = resolveCallSiteLine(frame, entry.signature());
      children.add(buildChildNode(entry.signature(), entry.classification(), csLine));
    }
    node.put(F_CHILDREN, children);

    return node;
  }

  private final BytecodeTracer tracer;

  public ForwardTracer(BytecodeTracer tracer) {
    this.tracer = tracer;
  }

  public Map<String, Object> traceForward(
      String fromClass, String fromMethod, BytecodeTracer.FilterConfig filter) throws IOException {
    return traceForwardFromMethod(
        tracer.resolveMethodByName(fromClass, fromMethod), fromClass, -1, filter);
  }

  public Map<String, Object> traceForward(
      String fromClass, int fromLine, BytecodeTracer.FilterConfig filter) throws IOException {
    return traceForwardFromMethod(
        tracer.resolveMethod(fromClass, fromLine), fromClass, fromLine, filter);
  }

  private Map<String, Object> traceForwardFromMethod(
      SootMethod entryMethod, String fromClass, int fromLine, BytecodeTracer.FilterConfig filter)
      throws IOException {
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

    // Pass 1 — Discover
    System.err.println("Discovering reachable methods from " + entrySig + "...");
    DiscoveryResult discovery =
        discoverReachable(entrySig, callerToCallees, sigToMethod.keySet(), filter);
    System.err.println("Discovered: " + discovery.normalMethods().size() + " methods");

    // Pass 2 — Build root
    System.err.println("Building CFGs...");
    Map<String, Object> root = buildMethodCFG(entrySig, sigToMethod, discovery);
    root.put(F_FROM_CLASS, fromClass);
    root.put(F_FROM_LINE, fromLine);

    // Pass 2 — Build refIndex (all NORMAL methods except root)
    Map<String, Object> refIndex = new LinkedHashMap<>();
    for (String sig : discovery.normalMethods()) {
      if (sig.equals(entrySig)) continue;
      refIndex.put(sig, buildMethodCFG(sig, sigToMethod, discovery));
    }

    // Envelope
    Map<String, Object> envelope = new LinkedHashMap<>();
    envelope.put(F_TRACE, root);
    envelope.put(F_REF_INDEX, refIndex);

    System.err.println("Done: " + (refIndex.size() + 1) + " method CFGs");
    return envelope;
  }

  @SuppressWarnings("unchecked")
  private Map<String, List<String>> loadForwardCallGraph() throws IOException {
    if (tracer.getCallGraphCache() != null && Files.exists(tracer.getCallGraphCache())) {
      System.err.println("Loading call graph from " + tracer.getCallGraphCache() + "...");
      ObjectMapper cgMapper = new ObjectMapper();
      Map<String, Object> raw = cgMapper.readValue(tracer.getCallGraphCache().toFile(), Map.class);
      Map<String, List<String>> graph =
          raw.containsKey("callees")
              ? (Map<String, List<String>>) raw.get("callees")
              : (Map<String, List<String>>) (Object) raw;
      System.err.println("Loaded " + graph.size() + " caller entries");
      return graph;
    }
    throw new RuntimeException("Call graph cache not found. Run `buildcg` first.");
  }

  /** Build block-level CFG trace from a method body. */
  Map<String, Object> buildBlockTrace(SootMethod method) {
    Body body = method.getBody();
    StmtGraph<?> stmtGraph = body.getStmtGraph();
    List<? extends BasicBlock<?>> blocks = stmtGraph.getBlocksSorted();
    if (blocks.isEmpty()) return Map.of("blocks", List.of(), "traps", List.of());

    Map<Stmt, String> stmtToBlockId = new LinkedHashMap<>();
    for (int i = 0; i < blocks.size(); i++) {
      stmtToBlockId.put(blocks.get(i).getHead(), "B" + i);
    }

    Map<String, Map<String, Object>> trapsMap = new LinkedHashMap<>();
    List<Map<String, Object>> blockList = new ArrayList<>();
    List<Map<String, Object>> edgeList = new ArrayList<>();

    for (int i = 0; i < blocks.size(); i++) {
      BasicBlock<?> block = blocks.get(i);
      String blockId = "B" + i;
      Map<String, Object> blockMap = new LinkedHashMap<>();
      blockMap.put("id", blockId);

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

      // Build top-level edges
      List<? extends BasicBlock<?>> successors = block.getSuccessors();
      boolean isBranch = block.getTail() instanceof JIfStmt && successors.size() == 2;
      for (int si = 0; si < successors.size(); si++) {
        String succId = stmtToBlockId.get(successors.get(si).getHead());
        if (succId != null) {
          Map<String, Object> edge = new LinkedHashMap<>();
          edge.put("fromBlock", blockId);
          edge.put("toBlock", succId);
          if (isBranch) {
            edge.put("label", si == 0 ? "T" : "F");
          }
          edgeList.add(edge);
        }
      }

      // Collect exceptional successors into centralized traps list
      stmtGraph
          .exceptionalSuccessors(block.getTail())
          .forEach(
              (type, succStmt) -> {
                BasicBlock<?> succBlock = stmtGraph.getBlockOf(succStmt);
                if (succBlock != null) {
                  String succId = stmtToBlockId.get(succBlock.getHead());
                  if (succId != null) {
                    String trapKey = succId + ":" + type;
                    Map<String, Object> trap =
                        trapsMap.computeIfAbsent(
                            trapKey,
                            k -> {
                              Map<String, Object> m = new LinkedHashMap<>();
                              m.put("handler", succId);
                              m.put("type", type.toString());
                              m.put("coveredBlocks", new ArrayList<String>());
                              return m;
                            });
                    @SuppressWarnings("unchecked")
                    List<String> covered = (List<String>) trap.get("coveredBlocks");
                    covered.add(blockId);
                  }
                }
              });

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

    Map<String, Object> result = new LinkedHashMap<>();
    result.put("blocks", blockList);
    result.put("edges", edgeList);

    // Build successor lookup for BFS from edge list
    Map<String, List<String>> succMap = new LinkedHashMap<>();
    for (Map<String, Object> edge : edgeList) {
      String from = (String) edge.get("fromBlock");
      String to = (String) edge.get("toBlock");
      succMap.computeIfAbsent(from, k -> new ArrayList<>()).add(to);
    }

    // Compute normal flow: blocks reachable from method entry via normal successors.
    // Handler entries are only reachable via exceptional edges, so they won't appear here.
    Set<String> normalFlow = new LinkedHashSet<>();
    Queue<String> nfQueue = new ArrayDeque<>();
    nfQueue.add("B0");
    while (!nfQueue.isEmpty()) {
      String current = nfQueue.poll();
      if (normalFlow.add(current)) {
        for (String s : succMap.getOrDefault(current, List.of())) {
          if (!normalFlow.contains(s)) nfQueue.add(s);
        }
      }
    }

    // Identify handler blocks for each trap (reachability from handler start,
    // stopping at normal-flow blocks to avoid including post-handler merge points)
    for (Map<String, Object> trap : trapsMap.values()) {
      String handlerId = (String) trap.get("handler");
      Set<String> handlerBlocks = new LinkedHashSet<>();
      Queue<String> queue = new ArrayDeque<>();
      queue.add(handlerId);

      while (!queue.isEmpty()) {
        String current = queue.poll();
        if (handlerBlocks.add(current)) {
          for (String s : succMap.getOrDefault(current, List.of())) {
            if (!normalFlow.contains(s) && !handlerBlocks.contains(s)) {
              queue.add(s);
            }
          }
        }
      }
      trap.put("handlerBlocks", new ArrayList<>(handlerBlocks));
    }

    // --- Gap-fill: add intermediate blocks missing from coveredBlocks ---
    Map<String, Set<String>> predMap = buildPredecessorMap(succMap);
    Set<String> allHandlerEntries = new HashSet<>();
    for (Map<String, Object> trap : trapsMap.values()) {
      allHandlerEntries.add((String) trap.get("handler"));
    }
    for (Map<String, Object> trap : trapsMap.values()) {
      @SuppressWarnings("unchecked")
      List<String> coveredList = (List<String>) trap.get("coveredBlocks");
      Set<String> filled =
          fillCoverageGaps(new LinkedHashSet<>(coveredList), succMap, predMap, allHandlerEntries);
      trap.put("coveredBlocks", new ArrayList<>(filled));
    }

    // --- Detect inlined handler copies (e.g., normal-path finally blocks) ---
    Map<String, Map<String, Object>> blockById = new LinkedHashMap<>();
    for (Map<String, Object> b : blockList) {
      blockById.put((String) b.get("id"), b);
    }
    Set<String> allAssigned = new HashSet<>();
    for (Map<String, Object> trap : trapsMap.values()) {
      @SuppressWarnings("unchecked")
      List<String> hb = (List<String>) trap.get("handlerBlocks");
      @SuppressWarnings("unchecked")
      List<String> cb = (List<String>) trap.get("coveredBlocks");
      allAssigned.addAll(hb);
      allAssigned.addAll(cb);
    }
    for (Map<String, Object> trap : trapsMap.values()) {
      String handlerId = (String) trap.get("handler");
      Map<String, Object> handlerBlock = blockById.get(handlerId);
      if (handlerBlock == null) continue;
      Set<Integer> handlerLines = sourceLines(handlerBlock);
      if (handlerLines.isEmpty()) continue;
      @SuppressWarnings("unchecked")
      List<String> hblocks = (List<String>) trap.get("handlerBlocks");
      for (Map<String, Object> b : blockList) {
        String bid = (String) b.get("id");
        if (allAssigned.contains(bid)) continue;
        Set<Integer> blines = sourceLines(b);
        if (!blines.isEmpty() && handlerLines.containsAll(blines)) {
          hblocks.add(bid);
          allAssigned.add(bid);
        }
      }
    }

    result.put("traps", new ArrayList<>(trapsMap.values()));
    return result;
  }

  /** Extract positive source line numbers from a block's stmts. */
  @SuppressWarnings("unchecked")
  static Set<Integer> sourceLines(Map<String, Object> blockMap) {
    Set<Integer> lines = new LinkedHashSet<>();
    for (Map<String, Object> stmt : (List<Map<String, Object>>) blockMap.get("stmts")) {
      int line = ((Number) stmt.get("line")).intValue();
      if (line > 0) lines.add(line);
    }
    return lines;
  }

  /** Invert a successor map to produce a predecessor map. */
  static Map<String, Set<String>> buildPredecessorMap(Map<String, List<String>> succMap) {
    Map<String, Set<String>> predMap = new LinkedHashMap<>();
    for (Map.Entry<String, List<String>> entry : succMap.entrySet()) {
      for (String succ : entry.getValue()) {
        predMap.computeIfAbsent(succ, k -> new LinkedHashSet<>()).add(entry.getKey());
      }
    }
    return predMap;
  }

  /**
   * Fill gaps in trap coverage. A block is added if it can reach a covered block going forward AND
   * can be reached from a covered block going backward, without crossing handler entries. Returns a
   * new set; does not mutate the input.
   */
  static Set<String> fillCoverageGaps(
      Set<String> coveredBlocks,
      Map<String, List<String>> succMap,
      Map<String, Set<String>> predMap,
      Set<String> handlerEntries) {
    // Forward reachable: blocks reachable from any covered block via successors
    Set<String> forwardReachable = bfsReachable(coveredBlocks, succMap, handlerEntries);
    // Backward reachable: blocks that can reach a covered block via predecessors
    Map<String, List<String>> predListMap = new LinkedHashMap<>();
    for (Map.Entry<String, Set<String>> e : predMap.entrySet()) {
      predListMap.put(e.getKey(), new ArrayList<>(e.getValue()));
    }
    Set<String> backwardReachable = bfsReachable(coveredBlocks, predListMap, handlerEntries);

    Set<String> result = new LinkedHashSet<>(coveredBlocks);
    for (String block : forwardReachable) {
      if (backwardReachable.contains(block) && !handlerEntries.contains(block)) {
        result.add(block);
      }
    }

    // Entry blocks (no predecessors) that flow directly into a covered block
    for (Map.Entry<String, List<String>> entry : succMap.entrySet()) {
      String block = entry.getKey();
      if (result.contains(block) || handlerEntries.contains(block)) continue;
      if (predMap.containsKey(block)) continue; // has predecessors — not an entry block
      for (String succ : entry.getValue()) {
        if (result.contains(succ)) {
          result.add(block);
          break;
        }
      }
    }

    return result;
  }

  /** BFS from seed blocks through adjacency map, not crossing blocked entries. */
  private static Set<String> bfsReachable(
      Set<String> seeds, Map<String, List<String>> adjMap, Set<String> blocked) {
    Set<String> visited = new LinkedHashSet<>();
    Queue<String> queue = new ArrayDeque<>(seeds);
    while (!queue.isEmpty()) {
      String current = queue.poll();
      if (visited.add(current)) {
        for (String next : adjMap.getOrDefault(current, List.of())) {
          if (!visited.contains(next) && !blocked.contains(next)) {
            queue.add(next);
          }
        }
      }
    }
    return visited;
  }
}
