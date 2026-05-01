package tools.bytecode.cli;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import tools.bytecode.BwdSliceBuilder;
import tools.bytecode.artifact.Artifact;
import tools.bytecode.artifact.CalltreeEdge;
import tools.bytecode.artifact.CalltreeGraph;
import tools.bytecode.artifact.CalltreeNode;
import tools.bytecode.artifact.DdgEdge;
import tools.bytecode.artifact.DdgGraph;
import tools.bytecode.artifact.DdgNode;
import tools.bytecode.artifact.EdgeInfo;
import tools.bytecode.artifact.HeapEdge;
import tools.bytecode.artifact.LocalEdge;

@Command(
    name = "bwd-slice",
    mixinStandardHelpOptions = true,
    description = {
      "Perform a backward interprocedural data dependency slice on a ddg-inter-cfg artifact.",
      "Input: stdin by default, or --input <file>",
      "Output: stdout by default, or --output <file>"
    })
class BwdSliceCommand extends BaseCommand {

  @Option(names = "--input", description = "Read ddg-inter-cfg JSON from file instead of stdin")
  Path input;

  @Option(names = "--method", required = true, description = "Seed method signature")
  String method;

  @Option(names = "--local-var", required = true, description = "Seed Jimple local variable name")
  String localVar;

  @Override
  public void run() {
    try {
      Map<String, Object> legacyInput = readLegacyFormat();
      Artifact artifact = convertLegacyToArtifact(legacyInput);
      Map<String, Object> result = new BwdSliceBuilder().build(artifact, method, localVar);
      writeOutput(result);
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> readLegacyFormat() throws IOException {
    if (input != null) {
      return mapper.readValue(input.toFile(), Map.class);
    }
    return mapper.readValue(System.in, Map.class);
  }

  @SuppressWarnings("unchecked")
  private Artifact convertLegacyToArtifact(Map<String, Object> legacyInput) {
    // Extract metadata and convert to String values
    Map<String, Object> metadataObj =
        (Map<String, Object>) legacyInput.getOrDefault("metadata", Map.of());
    Map<String, String> metadata = new java.util.LinkedHashMap<>();
    for (var entry : metadataObj.entrySet()) {
      metadata.put(entry.getKey(), String.valueOf(entry.getValue()));
    }

    // Reconstruct calltree from legacy nodes and calls
    Map<String, Object> nodesMap =
        (Map<String, Object>) legacyInput.getOrDefault("nodes", Map.of());
    List<Map<String, Object>> callsList =
        (List<Map<String, Object>>) legacyInput.getOrDefault("calls", List.of());

    // Build calltree nodes from legacy nodes
    List<CalltreeNode> calltreeNodes =
        nodesMap.entrySet().stream()
            .map(
                entry ->
                    new CalltreeNode(
                        (String) entry.getKey(),
                        (String) ((Map<String, Object>) entry.getValue()).get("class"),
                        (String) ((Map<String, Object>) entry.getValue()).get("method")))
            .toList();

    // Build calltree edges from legacy calls
    List<CalltreeEdge> calltreeEdges =
        callsList.stream()
            .map(call -> new CalltreeEdge((String) call.get("from"), (String) call.get("to")))
            .toList();

    CalltreeGraph calltree = new CalltreeGraph(calltreeNodes, calltreeEdges);

    // Reconstruct DDG from legacy ddgs map
    Map<String, Map<String, Object>> ddgsMap =
        (Map<String, Map<String, Object>>) legacyInput.getOrDefault("ddgs", Map.of());

    List<DdgNode> ddgNodes = new java.util.ArrayList<>();
    List<DdgEdge> ddgEdges = new java.util.ArrayList<>();

    for (var methodEntry : ddgsMap.entrySet()) {
      String methodSig = methodEntry.getKey();
      Map<String, Object> methodDdg = methodEntry.getValue();

      List<Map<String, Object>> methodNodes =
          (List<Map<String, Object>>) methodDdg.getOrDefault("nodes", List.of());
      List<Map<String, Object>> methodEdges =
          (List<Map<String, Object>>) methodDdg.getOrDefault("edges", List.of());

      // Convert nodes
      for (Map<String, Object> node : methodNodes) {
        String kind = (String) node.getOrDefault("kind", "ASSIGN");
        @SuppressWarnings("unchecked")
        Map<String, String> callMap =
            node.containsKey("call") ? (Map<String, String>) node.get("call") : Map.of();
        DdgNode ddgNode =
            new DdgNode(
                (String) node.get("id"),
                methodSig,
                (String) node.getOrDefault("stmt_id", ""),
                (String) node.get("stmt"),
                ((Number) node.getOrDefault("line", 0)).intValue(),
                tools.bytecode.artifact.StmtKind.valueOf(kind),
                callMap);
        ddgNodes.add(ddgNode);
      }

      // Convert edges
      for (Map<String, Object> edge : methodEdges) {
        Map<String, Object> edgeInfo =
            (Map<String, Object>) edge.getOrDefault("edge_info", Map.of());
        String kind = (String) edgeInfo.getOrDefault("kind", "LOCAL");

        EdgeInfo ei;
        if ("HEAP".equals(kind)) {
          String fieldSig = (String) edgeInfo.get("field_sig");
          ei = new HeapEdge(fieldSig);
        } else {
          ei = new LocalEdge(); // LOCAL edges
        }

        DdgEdge ddgEdge = new DdgEdge((String) edge.get("from"), (String) edge.get("to"), ei);
        ddgEdges.add(ddgEdge);
      }
    }

    DdgGraph ddg = new DdgGraph(ddgNodes, ddgEdges);
    return new Artifact(metadata, calltree, ddg);
  }
}
