package tools.source.icfg;

import fr.inria.controlflow.BranchKind;
import fr.inria.controlflow.ControlFlowEdge;
import fr.inria.controlflow.ControlFlowGraph;
import fr.inria.controlflow.ControlFlowNode;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.visitor.filter.TypeFilter;

public class IcfgBuilder {

  public InterproceduralCfg build(
      String className,
      String methodName,
      ScipIndex index,
      SpoonMethodCfgCache cache,
      IcfgConfig config) {
    SourceLocation loc = index.locationOf(className, methodName);
    ControlFlowGraph baseCfg = cache.cfgFor(className, loc.startLine());
    String symbol = toSymbol(className, methodName);
    return expand(className, symbol, baseCfg, 0, index, cache, config);
  }

  private InterproceduralCfg expand(
      String fqn,
      String symbol,
      ControlFlowGraph cfg,
      int depth,
      ScipIndex index,
      SpoonMethodCfgCache cache,
      IcfgConfig config) {

    Set<IcfgNode> nodes = new LinkedHashSet<>();
    Set<IcfgEdge> edges = new LinkedHashSet<>();
    IcfgNode entryNode = null;
    Set<IcfgNode> exitNodes = new LinkedHashSet<>();
    Map<ControlFlowNode, IcfgNode> nodeMap = new HashMap<>();

    for (ControlFlowNode cfn : cfg.vertexSet()) {
      IcfgNode node = new IcfgNode(cfn, symbol, depth);
      nodeMap.put(cfn, node);
      nodes.add(node);
      if (cfn.getKind() == BranchKind.BEGIN) entryNode = node;
      if (cfn.getKind() == BranchKind.EXIT) exitNodes.add(node);
    }

    for (ControlFlowEdge e : cfg.edgeSet()) {
      edges.add(
          new IcfgEdge(
              nodeMap.get(e.getSourceNode()), nodeMap.get(e.getTargetNode()), IcfgEdgeKind.INTRA));
    }

    if (depth < config.maxDepth()) {
      for (ControlFlowNode cfn : List.copyOf(cfg.vertexSet())) {
        if (cfn.getStatement() == null) continue;
        List<CtInvocation<?>> invocations =
            cfn.getStatement().getElements(new TypeFilter<>(CtInvocation.class));
        for (CtInvocation<?> inv : invocations) {
          expandInvocation(inv, cfn, nodeMap, nodes, edges, depth, index, cache, config);
        }
      }
    }

    return new InterproceduralCfg(nodes, edges, entryNode, exitNodes);
  }

  private void expandInvocation(
      CtInvocation<?> inv,
      ControlFlowNode callsiteCfn,
      Map<ControlFlowNode, IcfgNode> nodeMap,
      Set<IcfgNode> nodes,
      Set<IcfgEdge> edges,
      int depth,
      ScipIndex index,
      SpoonMethodCfgCache cache,
      IcfgConfig config) {

    var exec = inv.getExecutable();
    var declType = exec.getDeclaringType();
    if (declType == null) return;

    String calleeFqn = declType.getQualifiedName();
    String calleeMethod = exec.getSimpleName();
    if (config.stopCondition().test(calleeFqn)) return;
    if (!index.hasDefinition(calleeFqn, calleeMethod)) return;

    SourceLocation calleeLoc = index.locationOf(calleeFqn, calleeMethod);
    ControlFlowGraph calleeCfg;
    try {
      calleeCfg = cache.cfgFor(calleeFqn, calleeLoc.startLine());
    } catch (Exception e) {
      // Method may not have a body (abstract, etc.)
      return;
    }
    String calleeSymbol = toSymbol(calleeFqn, calleeMethod);
    InterproceduralCfg calleeIcfg =
        expand(calleeFqn, calleeSymbol, calleeCfg, depth + 1, index, cache, config);

    // Guard: calleeIcfg.entryNode() can be null
    if (calleeIcfg.entryNode() == null) return;

    nodes.addAll(calleeIcfg.vertexSet());
    edges.addAll(calleeIcfg.edgeSet());

    IcfgNode callsiteNode = nodeMap.get(callsiteCfn);
    // Guard: callsiteNode can be null
    if (callsiteNode == null) return;

    // Capture callsite's current INTRA successors before removing them
    Set<IcfgNode> callerSuccessors =
        edges.stream()
            .filter(e -> e.from().equals(callsiteNode) && e.kind() == IcfgEdgeKind.INTRA)
            .map(IcfgEdge::to)
            .collect(Collectors.toSet());

    // Remove INTRA edges bypassing the expansion
    edges.removeIf(e -> e.from().equals(callsiteNode) && e.kind() == IcfgEdgeKind.INTRA);

    // Add CALL edge
    edges.add(new IcfgEdge(callsiteNode, calleeIcfg.entryNode(), IcfgEdgeKind.CALL));

    // Add RETURN edges (skip if no exit nodes, e.g., abstract methods or stubs)
    if (calleeIcfg.exitNodes().isEmpty()) {
      System.err.println(
          "WARN: callee " + calleeSymbol + " has no exit nodes; RETURN edges skipped");
      return;
    }
    for (IcfgNode calleeExit : calleeIcfg.exitNodes()) {
      for (IcfgNode callerSucc : callerSuccessors) {
        edges.add(new IcfgEdge(calleeExit, callerSucc, IcfgEdgeKind.RETURN));
      }
    }
  }

  private static String toSymbol(String fqn, String methodName) {
    return fqn.replace('.', '/') + "#" + methodName;
  }
}
