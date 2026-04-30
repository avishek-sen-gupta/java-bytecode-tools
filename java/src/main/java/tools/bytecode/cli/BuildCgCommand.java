package tools.bytecode.cli;

import java.nio.file.Files;
import java.util.LinkedHashMap;
import java.util.Map;
import picocli.CommandLine.Command;
import tools.bytecode.CallGraphBuilder;
import tools.bytecode.CallGraphBuilder.CallGraphResult;

@Command(
    name = "buildcg",
    mixinStandardHelpOptions = true,
    description = {
      "Build the whole-program call graph from compiled .class files.",
      "",
      "Output: JSON object with:",
      "  callees   — map of caller signature → list of callee signatures",
      "  lineIndex — map of signature → {lineStart, lineEnd}",
      "",
      "The output file is consumed by xtrace (--call-graph), frames (--call-graph),",
      "and calltree (--callgraph). Build it once and reuse; rebuild only when classes change."
    })
class BuildCgCommand extends BaseCommand {

  @Override
  public void run() {
    try {
      var tracer = createTracer();
      CallGraphResult result = new CallGraphBuilder(tracer).buildCallGraph();
      Map<String, Object> output = new LinkedHashMap<>();
      output.put("callees", result.graph());
      output.put("lineIndex", result.lineIndex());
      if (this.output != null) {
        Files.createDirectories(this.output.getParent());
        mapper.writeValue(this.output.toFile(), output);
        System.err.println("Wrote call graph to " + this.output);
      } else {
        System.out.println(mapper.writeValueAsString(output));
      }
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
}
