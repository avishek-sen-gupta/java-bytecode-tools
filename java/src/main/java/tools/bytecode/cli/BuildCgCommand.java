package tools.bytecode.cli;

import java.nio.file.Files;
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
      CallGraphBuilder.CallGraphResult result = new CallGraphBuilder(tracer).buildCallGraph();
      Map<String, Object> out = new java.util.LinkedHashMap<>();
      out.put("callees", result.graph());
      out.put("callsites", result.callsites());
      if (output != null) {
        Files.createDirectories(output.getParent());
        mapper.writeValue(output.toFile(), out);
        System.err.println("Wrote call graph to " + output);
      } else {
        System.out.println(mapper.writeValueAsString(out));
      }
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
}
