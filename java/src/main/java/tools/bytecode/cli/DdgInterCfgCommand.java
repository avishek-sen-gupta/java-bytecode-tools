package tools.bytecode.cli;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import tools.bytecode.DdgInterCfgArtifactBuilder;

@Command(
    name = "ddg-inter-cfg",
    mixinStandardHelpOptions = true,
    description = {
      "Read a flat fw-calltree graph and emit a compound {nodes, calls, ddgs, metadata} artifact.",
      "",
      "Input: stdin by default, or --input <file>",
      "Output: stdout by default, or --output <file>"
    })
class DdgInterCfgCommand extends BaseCommand {

  @Option(names = "--input", description = "Read fw-calltree JSON from file instead of stdin")
  Path input;

  @Override
  public void run() {
    try {
      InputStream in = input != null ? Files.newInputStream(input) : System.in;
      @SuppressWarnings("unchecked")
      Map<String, Object> calltree = mapper.readValue(in, Map.class);
      Map<String, Object> result = new DdgInterCfgArtifactBuilder(createTracer()).build(calltree);
      writeOutput(result);
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
}
