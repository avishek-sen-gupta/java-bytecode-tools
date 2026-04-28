package tools.bytecode.cli;

import java.nio.file.Path;
import java.util.Map;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import tools.bytecode.BytecodeTracer;
import tools.bytecode.ForwardTracer;

@Command(
    name = "xtrace",
    mixinStandardHelpOptions = true,
    description = "Forward interprocedural trace — follow all callees from an entry point.")
class XtraceCommand extends BaseCommand {

  @Option(names = "--from", required = true, description = "Entry-point class")
  String fromClass;

  @Option(names = "--from-line", required = true, description = "Source line in --from class")
  int fromLine;

  @Option(names = "--filter", description = "JSON filter file with allow/stop prefix arrays")
  Path filterFile;

  @Option(names = "--call-graph", required = true, description = "Path to call graph JSON file")
  Path callGraphFile;

  @Override
  public void run() {
    try {
      var tracer = createTracer();
      tracer.setCallGraphCache(callGraphFile);
      BytecodeTracer.FilterConfig filter = BytecodeTracer.FilterConfig.load(filterFile);
      Map<String, Object> result =
          new ForwardTracer(tracer).traceForward(fromClass, fromLine, filter);
      writeOutput(result);
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
}
