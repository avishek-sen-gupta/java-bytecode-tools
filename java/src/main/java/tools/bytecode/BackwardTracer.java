package tools.bytecode;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Files;
import java.util.*;
import java.util.stream.Collectors;
import sootup.core.model.SootMethod;
import sootup.java.core.JavaSootClass;

/**
 * Backward (bottom-up) interprocedural tracer. BFS backward from a target method through the call
 * graph to find all entry points that can reach it, enumerating all distinct call chains.
 */
public class BackwardTracer {

  private final BytecodeTracer tracer;
  private Map<String, SootMethod> sigToMethod;

  public BackwardTracer(BytecodeTracer tracer) {
    this.tracer = tracer;
  }

  public Map<String, Object> traceInterprocedural(
      String fromClass,
      int fromLine,
      String toClass,
      int toLine,
      int maxDepth,
      boolean collapse,
      boolean flat,
      BytecodeTracer.FilterConfig filter)
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
    List<List<BytecodeTracer.CallFrame>> completedChains = new ArrayList<>();
    int maxPaths = 50;

    for (String entrySig : reachedEntries) {
      Deque<Map.Entry<String, List<String>>> stack = new ArrayDeque<>();
      stack.push(Map.entry(entrySig, new ArrayList<>(List.of(entrySig))));

      while (!stack.isEmpty() && completedChains.size() < maxPaths) {
        var top = stack.pop();
        String current = top.getKey();
        List<String> path = top.getValue();

        if (current.equals(targetSig)) {
          List<BytecodeTracer.CallFrame> chain = new ArrayList<>();
          for (String s : path) {
            SootMethod method = sigToMethod.get(s);
            if (method != null) {
              chain.add(flat ? tracer.buildFlatFrame(method, s) : tracer.buildFrame(method, s));
            }
          }
          if (!chain.isEmpty()) {
            completedChains.add(chain);
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

    return buildResult(
        fromClass, fromLine, toClass, toLine, collapse, flat, filter, completedChains);
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
      boolean collapse,
      boolean flat,
      BytecodeTracer.FilterConfig filter,
      List<List<BytecodeTracer.CallFrame>> completedChains) {
    Map<String, Object> result = new LinkedHashMap<>();
    if (fromClass != null) {
      result.put("fromClass", fromClass);
      result.put("fromLine", fromLine);
    }
    result.put("toClass", toClass);
    result.put("toLine", toLine);

    Set<String> globalVisited = new HashSet<>();

    if (completedChains.isEmpty()) {
      result.put("found", false);
      result.put("chains", Collections.emptyList());
    } else if (collapse) {
      result.put("found", true);
      result.put("collapsed", true);
      result.put("groups", buildCollapsedGroups(completedChains, flat, filter, globalVisited));
    } else {
      result.put("found", true);
      result.put("chains", buildChainMaps(completedChains, flat, filter, globalVisited));
    }
    return result;
  }

  private List<Map<String, Object>> buildCollapsedGroups(
      List<List<BytecodeTracer.CallFrame>> completedChains,
      boolean flat,
      BytecodeTracer.FilterConfig filter,
      Set<String> globalVisited) {
    Map<String, List<BytecodeTracer.CallFrame>> suffixToChain = new LinkedHashMap<>();
    Map<String, List<String>> suffixToEntries = new LinkedHashMap<>();

    for (List<BytecodeTracer.CallFrame> chain : completedChains) {
      String suffixKey;
      if (chain.size() > 1) {
        suffixKey =
            chain.subList(1, chain.size()).stream()
                .map(BytecodeTracer.CallFrame::methodSignature)
                .collect(Collectors.joining(" -> "));
      } else {
        suffixKey = chain.get(0).methodSignature();
      }
      suffixToChain.putIfAbsent(
          suffixKey, chain.size() > 1 ? chain.subList(1, chain.size()) : chain);
      suffixToEntries
          .computeIfAbsent(suffixKey, k -> new ArrayList<>())
          .add(chain.get(0).className() + "." + chain.get(0).methodName());
    }

    List<Map<String, Object>> groups = new ArrayList<>();
    for (var entry : suffixToChain.entrySet()) {
      Map<String, Object> group = new LinkedHashMap<>();
      List<String> entries = suffixToEntries.get(entry.getKey());
      group.put("entryPoints", entries);
      group.put("entryCount", entries.size());
      group.put("chain", buildFrameMaps(entry.getValue(), flat, filter, globalVisited));
      groups.add(group);
    }
    return groups;
  }

  private List<List<Map<String, Object>>> buildChainMaps(
      List<List<BytecodeTracer.CallFrame>> completedChains,
      boolean flat,
      BytecodeTracer.FilterConfig filter,
      Set<String> globalVisited) {
    List<List<Map<String, Object>>> chainMaps = new ArrayList<>();
    for (List<BytecodeTracer.CallFrame> chain : completedChains) {
      chainMaps.add(buildFrameMaps(chain, flat, filter, globalVisited));
    }
    return chainMaps;
  }

  /**
   * Builds the identity + line metadata portion of a frame map, and marks it as a ref if the
   * signature has already been visited (deduplicating heavy block data across chains). Line
   * metadata is always included — only sourceTrace/blocks/edges/traps are suppressed on ref frames.
   */
  static Map<String, Object> buildRefAwareFrameMap(
      BytecodeTracer.CallFrame f, Set<String> globalVisited, boolean includeSourceLineCount) {
    Map<String, Object> fm = new LinkedHashMap<>();
    fm.put("class", f.className());
    fm.put("method", f.methodName());
    fm.put("methodSignature", f.methodSignature());
    fm.put("lineStart", f.entryLine());
    fm.put("lineEnd", f.exitLine());
    if (includeSourceLineCount) {
      fm.put("sourceLineCount", f.exitLine() - f.entryLine() + 1);
    }
    if (globalVisited.contains(f.methodSignature())) {
      fm.put("ref", true);
    } else {
      globalVisited.add(f.methodSignature());
    }
    return fm;
  }

  private List<Map<String, Object>> buildFrameMaps(
      List<BytecodeTracer.CallFrame> chain,
      boolean flat,
      BytecodeTracer.FilterConfig filter,
      Set<String> globalVisited) {
    List<Map<String, Object>> frameMaps = new ArrayList<>();
    for (int fi = 0; fi < chain.size(); fi++) {
      BytecodeTracer.CallFrame f = chain.get(fi);

      Map<String, Object> fm = buildRefAwareFrameMap(f, globalVisited, !flat);

      if (fi < chain.size() - 1) {
        int csLine = BytecodeTracer.findCallSiteLine(f, chain.get(fi + 1));
        if (csLine > 0) fm.put("callSiteLine", csLine);
      }

      if (!flat && fm.get("ref") == null) {
        fm.put("sourceTrace", f.sourceTrace());

        // Respect filter: only add blocks and traps if allowed
        if (filter == null || filter.shouldRecurse(f.className())) {
          SootMethod method = sigToMethod.get(f.methodSignature());
          if (method != null) {
            Map<String, Object> blockInfo = new ForwardTracer(tracer).buildBlockTrace(method);
            fm.put("blocks", blockInfo.get("blocks"));
            fm.put("edges", blockInfo.get("edges"));
            fm.put("traps", blockInfo.get("traps"));
          }
        } else {
          fm.put("filtered", true);
        }
      }
      frameMaps.add(fm);
    }
    return frameMaps;
  }
}
