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
      "Read a flat fw-calltree graph and emit a compound {nodes, calls, ddgs, metadata} artifact.",
      "Input: stdin by default, or --input <file>",
      "Output: stdout by default, or --output <file>"
    })
class DdgInterCfgCommand extends BaseCommand {

  @Option(names = "--input", description = "Read fw-calltree JSON from file instead of stdin")
  Path input;

  @Override
  public void run() {
    try {
      Map<String, Object> inputGraph = readInputGraph();
      Artifact artifact = new DdgInterCfgArtifactBuilder(createTracer()).build(inputGraph);
      writeOutput(artifact);
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
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
