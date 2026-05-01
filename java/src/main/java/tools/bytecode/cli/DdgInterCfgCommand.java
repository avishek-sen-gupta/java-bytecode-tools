package tools.bytecode.cli;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import tools.bytecode.DdgInterCfgArtifactBuilder;
import tools.bytecode.artifact.Artifact;

@Command(
    name = "ddg-inter-cfg",
    mixinStandardHelpOptions = true,
    description = {
      "Read a fw-calltree JSON artifact and emit a typed {metadata, calltree, ddg} artifact.",
      "Input: stdin by default, or --input <file>",
      "Output: stdout by default, or --output <file>"
    })
class DdgInterCfgCommand extends BaseCommand {

  @Option(names = "--input", description = "Read fw-calltree JSON from file instead of stdin")
  Path input;

  @Option(
      names = "--unbounded",
      description =
          "Widen heap dependency search to all Qilin-reachable methods (default: fw-calltree scope"
              + " only)")
  boolean unbounded;

  @Override
  public void run() {
    try {
      Map<String, Object> inputGraph = readInputGraph();
      tools.bytecode.BytecodeTracer tracer = createTracer();
      tools.bytecode.FieldDepEnricher enricher = buildEnricher(tracer, inputGraph);
      Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, enricher).build(inputGraph);
      Map<String, Object> legacyOutput = toLegacyFormat(artifact, inputGraph);
      writeOutput(legacyOutput);
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }

  @SuppressWarnings("unchecked")
  private tools.bytecode.FieldDepEnricher buildEnricher(
      tools.bytecode.BytecodeTracer tracer, Map<String, Object> input) {
    if (!unbounded) {
      return null;
    }

    Map<String, Object> inputMetadata =
        (Map<String, Object>) input.getOrDefault("metadata", Map.of());
    String root = (String) inputMetadata.getOrDefault("root", "");
    if (root.isEmpty()) {
      return null;
    }

    // Conservative may-alias: always true (sound over-approximation)
    // Full Qilin integration deferred to future work.
    return new tools.bytecode.FieldDepEnricher((sigA, localA, sigB, localB) -> true);
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> readInputGraph() throws IOException {
    if (input != null) {
      return mapper.readValue(input.toFile(), Map.class);
    }
    return mapper.readValue(System.in, Map.class);
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> toLegacyFormat(Artifact artifact, Map<String, Object> input) {
    Map<String, Object> output = new java.util.LinkedHashMap<>();

    // Preserve nodes and calls from input
    output.put("nodes", input.getOrDefault("nodes", Map.of()));
    output.put("calls", input.getOrDefault("calls", List.of()));

    // Add metadata with tool information
    Map<String, Object> metadata = new java.util.LinkedHashMap<>(artifact.metadata());
    metadata.put("tool", "ddg-inter-cfg");
    Map<String, Object> inputMetadata =
        (Map<String, Object>) input.getOrDefault("metadata", Map.of());
    if (inputMetadata.containsKey("tool")) {
      metadata.put("inputTool", inputMetadata.get("tool"));
    }
    output.put("metadata", metadata);

    // Build ddgs map: one entry per method signature
    Map<String, Object> ddgsMap = new java.util.LinkedHashMap<>();
    for (var calltreeNode : artifact.calltree().nodes()) {
      Map<String, Object> methodDdg = new java.util.LinkedHashMap<>();
      // Filter DDG nodes and edges for this method
      var nodesForMethod =
          artifact.ddg().nodes().stream()
              .filter(n -> n.method().equals(calltreeNode.id()))
              .collect(java.util.stream.Collectors.toList());
      var edgesForMethod =
          artifact.ddg().edges().stream()
              .filter(
                  e -> {
                    var src =
                        artifact.ddg().nodes().stream()
                            .filter(n -> n.id().equals(e.from()))
                            .findFirst();
                    return src.isPresent() && src.get().method().equals(calltreeNode.id());
                  })
              .collect(java.util.stream.Collectors.toList());
      methodDdg.put("nodes", nodesForMethod);
      methodDdg.put("edges", edgesForMethod);
      ddgsMap.put(calltreeNode.id(), methodDdg);
    }
    output.put("ddgs", ddgsMap);

    return output;
  }
}
