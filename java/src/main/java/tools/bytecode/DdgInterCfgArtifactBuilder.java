package tools.bytecode;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import sootup.core.model.SootMethod;
import tools.bytecode.artifact.Artifact;
import tools.bytecode.artifact.CalltreeEdge;
import tools.bytecode.artifact.CalltreeGraph;
import tools.bytecode.artifact.CalltreeNode;
import tools.bytecode.artifact.DdgEdge;
import tools.bytecode.artifact.DdgGraph;
import tools.bytecode.artifact.DdgNode;

public class DdgInterCfgArtifactBuilder {

  private final BytecodeTracer tracer;
  private final FieldDepEnricher enricher;

  public DdgInterCfgArtifactBuilder(BytecodeTracer tracer, FieldDepEnricher enricher) {
    this.tracer = tracer;
    this.enricher = enricher;
  }

  public DdgInterCfgArtifactBuilder(BytecodeTracer tracer) {
    this(tracer, null);
  }

  @SuppressWarnings("unchecked")
  public Artifact build(Map<String, Object> input) {
    Map<String, Object> nodes = (Map<String, Object>) input.get("nodes");
    if (nodes == null) throw new IllegalArgumentException("Missing 'nodes' in input");
    if (nodes.isEmpty()) throw new IllegalArgumentException("'nodes' must not be empty");

    Map<String, Object> inputMetadata =
        (Map<String, Object>) input.getOrDefault("metadata", Map.of());
    String root = (String) inputMetadata.getOrDefault("root", "");
    String inputTool = (String) inputMetadata.getOrDefault("tool", "");

    Map<String, String> metadata = new java.util.LinkedHashMap<>();
    metadata.put("root", root);
    metadata.put("tool", "ddg-inter-cfg");
    if (!inputTool.isEmpty()) {
      metadata.put("inputTool", inputTool);
    }

    List<Map<String, Object>> calls =
        (List<Map<String, Object>>) input.getOrDefault("calls", List.of());

    // Build calltree
    List<CalltreeNode> calltreeNodes = new ArrayList<>();
    for (String sig : nodes.keySet()) {
      Map<String, Object> nodeInfo = (Map<String, Object>) nodes.get(sig);
      String className = (String) nodeInfo.getOrDefault("class", "");
      String methodName = (String) nodeInfo.getOrDefault("method", "");
      calltreeNodes.add(new CalltreeNode(sig, className, methodName));
    }
    List<CalltreeEdge> calltreeEdges = new ArrayList<>();
    for (Map<String, Object> call : calls) {
      calltreeEdges.add(new CalltreeEdge((String) call.get("from"), (String) call.get("to")));
    }
    CalltreeGraph calltree = new CalltreeGraph(calltreeNodes, calltreeEdges);

    // Build DDG: global flat lists across all methods
    List<DdgNode> ddgNodes = new ArrayList<>();
    List<DdgEdge> ddgEdges = new ArrayList<>();

    DdgInterCfgMethodGraphBuilder methodBuilder = new DdgInterCfgMethodGraphBuilder();
    for (String sig : nodes.keySet()) {
      SootMethod method = tracer.resolveMethod(sig);
      if (!method.hasBody()) {
        throw new IllegalArgumentException("Resolved method has no body: " + sig);
      }
      DdgInterCfgMethodGraphBuilder.MethodDdgPayload payload = methodBuilder.build(method, sig);
      ddgNodes.addAll(payload.nodes());
      ddgEdges.addAll(payload.edges());
    }

    // Inter-procedural edges: PARAM + RETURN
    InterProcEdgeBuilder interProcBuilder = new InterProcEdgeBuilder();
    List<DdgEdge> interProcEdges = interProcBuilder.build(ddgNodes, ddgEdges, calls);
    ddgEdges.addAll(interProcEdges);

    Set<String> inScopeMethodSigs = new HashSet<>(nodes.keySet());
    DdgGraph rawDdg = new DdgGraph(ddgNodes, ddgEdges);
    DdgGraph enrichedDdg = enricher != null ? enricher.enrich(rawDdg, inScopeMethodSigs) : rawDdg;

    return new Artifact(metadata, calltree, enrichedDdg);
  }
}
