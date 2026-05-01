package tools.bytecode.cli;

import java.io.IOException;
import java.nio.file.Path;
import java.util.Map;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import tools.bytecode.BwdSliceBuilder;

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
      Map<String, Object> artifact = readArtifact();
      Map<String, Object> result = new BwdSliceBuilder().build(artifact, method, localVar);
      writeOutput(result);
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }

  @SuppressWarnings("unchecked")
  private Map<String, Object> readArtifact() throws IOException {
    if (input != null) {
      return mapper.readValue(input.toFile(), Map.class);
    }
    return mapper.readValue(System.in, Map.class);
  }
}
