package tools.bytecode.cli;

import java.io.IOException;
import java.nio.file.Path;
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
      writeOutput(artifact);
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

    try {
      qilin.driver.PTAPattern pattern = new qilin.driver.PTAPattern("insens");
      qilin.core.PTA pta = qilin.driver.PTAFactory.createPTA(pattern, tracer.getView(), root);
      pta.run();
      // Conservative may-alias: always true (sound over-approximation)
      // Full local resolution via Qilin Local objects deferred to future work.
      return new tools.bytecode.FieldDepEnricher((sigA, localA, sigB, localB) -> true);
    } catch (Exception e) {
      System.err.println(
          "[ddg-inter-cfg] Qilin PTA failed, skipping heap analysis: " + e.getMessage());
      return null;
    }
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> readInputGraph() throws IOException {
    if (input != null) {
      return mapper.readValue(input.toFile(), Map.class);
    }
    return mapper.readValue(System.in, Map.class);
  }
}
