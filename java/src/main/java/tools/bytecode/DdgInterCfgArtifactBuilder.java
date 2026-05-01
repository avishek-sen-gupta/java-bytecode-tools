package tools.bytecode;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import sootup.core.model.SootMethod;

public class DdgInterCfgArtifactBuilder {

  private final BytecodeTracer tracer;
  private final DdgInterCfgMethodGraphBuilder methodGraphBuilder =
      new DdgInterCfgMethodGraphBuilder();

  public DdgInterCfgArtifactBuilder(BytecodeTracer tracer) {
    this.tracer = tracer;
  }

  public Map<String, Object> build(Map<String, Object> input) {
    @SuppressWarnings("unchecked")
    Map<String, Object> nodes = (Map<String, Object>) input.get("nodes");
    if (nodes == null || nodes.isEmpty()) {
      throw new IllegalArgumentException("Input JSON must contain non-empty top-level 'nodes'");
    }

    @SuppressWarnings("unchecked")
    List<Map<String, Object>> calls =
        (List<Map<String, Object>>) input.getOrDefault("calls", List.of());

    Map<String, Object> ddgs = new LinkedHashMap<>();
    for (String methodSignature : nodes.keySet()) {
      SootMethod method = tracer.resolveMethod(methodSignature);
      if (!method.hasBody()) {
        throw new IllegalArgumentException("Resolved method has no body: " + methodSignature);
      }
      ddgs.put(methodSignature, methodGraphBuilder.build(method));
    }

    Map<String, Object> metadata = new LinkedHashMap<>();
    metadata.put("tool", "ddg-inter-cfg");
    Object inputMetadata = input.get("metadata");
    if (inputMetadata instanceof Map<?, ?> map && map.get("tool") != null) {
      metadata.put("inputTool", map.get("tool"));
    }
    metadata.put("methodCount", nodes.size());
    metadata.put("ddgCount", ddgs.size());

    Map<String, Object> output = new LinkedHashMap<>();
    output.put("nodes", nodes);
    output.put("calls", calls);
    output.put("ddgs", ddgs);
    output.put("metadata", metadata);
    return output;
  }
}
