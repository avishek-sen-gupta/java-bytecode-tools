package tools.bytecode.cli;

import java.nio.file.Path;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

@Command(
    name = "ddg-inter-cfg",
    mixinStandardHelpOptions = true,
    description = {
      "Read a flat fw-calltree graph and emit a compound {nodes, calls, ddgs, metadata} artifact.",
      "",
      "Scaffold only: runtime implementation will land in a later task.",
      "",
      "Input: stdin by default, or --input <file>",
      "Output: stdout by default, or --output <file>"
    })
class DdgInterCfgCommand extends BaseCommand {

  @Option(names = "--input", description = "Read fw-calltree JSON from file instead of stdin")
  Path input;

  @Override
  public void run() {
    System.err.println("Error: ddg-inter-cfg is not implemented yet.");
    System.exit(1);
  }
}
