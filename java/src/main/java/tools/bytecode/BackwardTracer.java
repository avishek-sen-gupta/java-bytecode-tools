package tools.bytecode;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.util.*;
import sootup.core.model.SootMethod;
import sootup.java.core.JavaSootClass;

/**
 * Backward (bottom-up) interprocedural tracer. BFS backward from a target method through the call
 * graph to find all entry points that can reach it, enumerating all distinct call chains.
 *
 * <p>Output is a lightweight tree: each chain is a nested list of frames (no CFG data), all chains
 * wrapped under a synthetic {@code "END"} root so the result is compatible with the {@code
 * ftrace-semantic} pipeline.
 */
public class BackwardTracer {

  private final BytecodeTracer tracer;
  private Map<String, SootMethod> sigToMethod;

  public BackwardTracer(BytecodeTracer tracer) {
    this.tracer = tracer;
  }

  public Map<String, Object> traceInterprocedural(
      String fromClass, int fromLine, String toClass, int toLine, int maxDepth, int maxChains)
      throws IOException {
    SootMethod targetMethod = tracer.resolveMethod(toClass, toLine);
    String targetSig = targetMethod.getSignature().toString();

    // Index all project methods
    this.sigToMethod = new LinkedHashMap<>();
    for (JavaSootClass cls : tracer.getProjectClasses()) {
      for (SootMethod method : cls.getMethods()) {
        if (!method.hasBody()) continue;
        sigToMethod.put(method.getSignature().toString(), method);
      }
    }
    System.err.println("Methods: " + sigToMethod.size());

    // Load and invert call graph (callee → callers)
    Map<String, List<String>> calleeToCallers = loadReverseCallGraph();

    // BFS backward from target
    Map<String, Set<String>> childToParents = new LinkedHashMap<>();
    Queue<String> queue = new ArrayDeque<>();
    Set<String> visited = new HashSet<>();

    queue.add(targetSig);
    visited.add(targetSig);
    childToParents.put(targetSig, new LinkedHashSet<>());

    Set<String> fromSigs = new HashSet<>();
    if (fromClass != null) {
      SootMethod fromMethod = tracer.resolveMethod(fromClass, fromLine);
      fromSigs.add(fromMethod.getSignature().toString());
    }

    List<String> reachedEntries = new ArrayList<>();
    int depth = 0;
    int levelSize = queue.size();

    while (!queue.isEmpty() && depth <= maxDepth) {
      String current = queue.poll();

      if (!fromSigs.isEmpty() && fromSigs.contains(current)) {
        reachedEntries.add(current);
      } else if (fromSigs.isEmpty()) {
        List<String> callers = calleeToCallers.get(current);
        if (callers == null || callers.isEmpty()) {
          reachedEntries.add(current);
        }
      }

      List<String> callers = calleeToCallers.get(current);
      if (callers != null) {
        for (String caller : callers) {
          childToParents.computeIfAbsent(caller, k -> new LinkedHashSet<>()).add(current);
          if (visited.add(caller)) {
            queue.add(caller);
          }
        }
      }

      if (--levelSize == 0) {
        depth++;
        levelSize = queue.size();
      }
    }

    // Enumerate ALL distinct paths from each entry → target via DFS
    List<Map<String, Object>> chainTrees = new ArrayList<>();
    int maxPaths = maxChains;

    for (String entrySig : reachedEntries) {
      Deque<Map.Entry<String, List<String>>> stack = new ArrayDeque<>();
      stack.push(Map.entry(entrySig, new ArrayList<>(List.of(entrySig))));

      while (!stack.isEmpty() && chainTrees.size() < maxPaths) {
        var top = stack.pop();
        String current = top.getKey();
        List<String> path = top.getValue();

        if (current.equals(targetSig)) {
          List<BytecodeTracer.CallFrame> callFrames =
              path.stream()
                  .filter(sigToMethod::containsKey)
                  .map(s -> tracer.buildFlatFrame(sigToMethod.get(s), s))
                  .toList();
          List<Map<String, Object>> frames = new ArrayList<>();
          for (int i = 0; i < callFrames.size(); i++) {
            BytecodeTracer.CallFrame cf = callFrames.get(i);
            int callSiteLine =
                i == 0 ? -1 : BytecodeTracer.findCallSiteLine(callFrames.get(i - 1), cf);
            frames.add(buildLightweightFrameMap(cf, callSiteLine));
          }
          if (!frames.isEmpty()) {
            chainTrees.add(nestFrames(frames));
          }
          continue;
        }

        Set<String> children = childToParents.get(current);
        if (children != null) {
          for (String child : children) {
            if (!path.contains(child)) {
              List<String> newPath = new ArrayList<>(path);
              newPath.add(child);
              stack.push(Map.entry(child, newPath));
            }
          }
        }
      }
    }

    return buildResult(fromClass, fromLine, toClass, toLine, chainTrees);
  }

  private Map<String, List<String>> loadReverseCallGraph() throws IOException {
    Map<String, List<String>> calleeToCallers = new LinkedHashMap<>();
    if (tracer.getCallGraphCache() != null && Files.exists(tracer.getCallGraphCache())) {
      System.err.println("Loading call graph from " + tracer.getCallGraphCache() + "...");
      ObjectMapper cgMapper = new ObjectMapper();
      @SuppressWarnings("unchecked")
      Map<String, List<String>> cached =
          cgMapper.readValue(tracer.getCallGraphCache().toFile(), Map.class);
      for (var entry : cached.entrySet()) {
        String callerSig = entry.getKey();
        for (String calleeSig : entry.getValue()) {
          calleeToCallers.computeIfAbsent(calleeSig, k -> new ArrayList<>()).add(callerSig);
        }
      }
      System.err.println("Loaded " + cached.size() + " caller entries");
    } else {
      throw new RuntimeException("Call graph cache not found. Run `buildcg` first.");
    }
    return calleeToCallers;
  }

  private Map<String, Object> buildResult(
      String fromClass,
      int fromLine,
      String toClass,
      int toLine,
      List<Map<String, Object>> chainTrees) {
    Map<String, Object> result = new LinkedHashMap<>();
    if (fromClass != null) {
      result.put("fromClass", fromClass);
      result.put("fromLine", fromLine);
    }
    result.put("toClass", toClass);
    result.put("toLine", toLine);
    result.put("found", !chainTrees.isEmpty());
    if (!chainTrees.isEmpty()) {
      Map<String, Object> syntheticRoot = new LinkedHashMap<>();
      syntheticRoot.put("synthetic", true);
      syntheticRoot.put("class", "END");
      syntheticRoot.put("children", chainTrees);
      result.put("trace", syntheticRoot);
    }
    return result;
  }

  /**
   * Builds a lightweight frame map: identity fields + line metadata only. No blocks, no ref.
   *
   * @param callSiteLine line in the caller where this frame is invoked; omitted when ≤ 0
   */
  static Map<String, Object> buildLightweightFrameMap(
      BytecodeTracer.CallFrame f, int callSiteLine) {
    Map<String, Object> fm = new LinkedHashMap<>();
    fm.put("class", f.className());
    fm.put("method", f.methodName());
    fm.put("methodSignature", f.methodSignature());
    fm.put("lineStart", f.entryLine());
    fm.put("lineEnd", f.exitLine());
    fm.put("sourceLineCount", f.exitLine() - f.entryLine() + 1);
    if (callSiteLine > 0) {
      fm.put("callSiteLine", callSiteLine);
    }
    return fm;
  }

  /**
   * Converts a flat list of frame maps into a nested tree: each frame becomes the parent of the
   * next via a single-element {@code children} list. Empty list returns empty map.
   */
  static Map<String, Object> nestFrames(List<Map<String, Object>> frames) {
    if (frames.isEmpty()) return new LinkedHashMap<>();
    Map<String, Object> head = new LinkedHashMap<>(frames.get(0));
    if (frames.size() == 1) return head;
    head.put("children", List.of(nestFrames(frames.subList(1, frames.size()))));
    return head;
  }
}
