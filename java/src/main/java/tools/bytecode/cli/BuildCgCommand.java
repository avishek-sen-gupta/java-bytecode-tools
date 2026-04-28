package tools.bytecode.cli;

import java.nio.file.Files;
import java.util.List;
import java.util.Map;
import picocli.CommandLine.Command;
import tools.bytecode.CallGraphBuilder;

@Command(
    name = "buildcg",
    mixinStandardHelpOptions = true,
    description = {
      "Build the whole-program call graph from compiled .class files.",
      "",
      "Output: JSON map of caller signature → list of callee signatures.",
      "  {\"<Class: ReturnType method(Args)>\": [\"<callee-sig>\", ...], ...}",
      "",
      "The output file is consumed by xtrace (--call-graph) and frames (--call-graph).",
      "Build it once and reuse; rebuild only when classes change."
    })
class BuildCgCommand extends BaseCommand {

  @Override
  public void run() {
    try {
      var tracer = createTracer();
      Map<String, List<String>> graph = new CallGraphBuilder(tracer).buildCallGraph();
      if (output != null) {
        Files.createDirectories(output.getParent());
        mapper.writeValue(output.toFile(), graph);
        System.err.println("Wrote call graph to " + output);
      } else {
        System.out.println(mapper.writeValueAsString(graph));
      }
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
}
