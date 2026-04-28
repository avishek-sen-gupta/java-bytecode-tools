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
    description = {
      "Forward interprocedural trace — DFS from an entry point through all reachable callees.",
      "",
      "Two-pass pipeline:",
      "  1. Discover — DFS over the call graph; classifies each reachable method as",
      "               normal, cycle, or filtered.",
      "  2. Build   — constructs a CFG-rich body for the root method; all other callees",
      "               are emitted as lightweight ref leaves with full bodies in refIndex.",
      "",
      "Output envelope: {\"trace\": <root-body>, \"refIndex\": {\"<sig>\": <body>, ...}}",
      "  ref      — non-root callee (body in refIndex; expand with ftrace-expand-refs)",
      "  cycle    — recursive edge; emitted as a leaf, not expanded",
      "  filtered — excluded by --filter; emitted as a leaf, not expanded",
      "",
      "Typical pipeline:",
      "  xtrace ... | ftrace-slice --to <class> | ftrace-expand-refs | ftrace-semantic |"
          + " ftrace-to-dot"
    })
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
