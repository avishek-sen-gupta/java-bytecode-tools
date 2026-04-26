package tools.bytecode.cli;

import picocli.CommandLine.Command;
import tools.bytecode.CallGraphBuilder;

@Command(
    name = "buildcg",
    mixinStandardHelpOptions = true,
    description = "Build the whole-program call graph from compiled .class files.")
class BuildCgCommand extends BaseCommand {

  @Override
  public void run() {
    try {
      if (output == null) {
        System.err.println("buildcg requires --output <file>");
        System.exit(1);
      }
      var tracer = createTracer();
      new CallGraphBuilder(tracer).buildCallGraph(output);
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
}
