package tools.bytecode.cli;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import tools.bytecode.BackwardTracer;
import tools.bytecode.BytecodeTracer;
import tools.bytecode.ForwardTracer;

@Command(
    name = "xtrace",
    mixinStandardHelpOptions = true,
    description = "Interprocedural trace — forward or backward through the call graph.")
class XtraceCommand extends BaseCommand {

  @Option(names = "--from", description = "Source class (entry point)")
  String fromClass;

  @Option(names = "--from-line", description = "Source line in --from class")
  Integer fromLine;

  @Option(names = "--to", description = "Target class")
  String toClass;

  @Option(names = "--to-line", description = "Target line in --to class")
  Integer toLine;

  @Option(names = "--depth", description = "Max backward trace depth", defaultValue = "5")
  int maxDepth;

  @Option(names = "--collapse", description = "Group paths sharing the same intermediate chain")
  boolean collapse;

  @Option(names = "--flat", description = "Flat stack-trace output (no sourceTrace/blocks, faster)")
  boolean flat;

  @Option(names = "--filter", description = "JSON filter file with allow/stop prefix arrays")
  Path filterFile;

  @Option(names = "--call-graph", required = true, description = "Path to call graph JSON file")
  Path callGraphFile;

  @Override
  public void run() {
    try {
      var tracer = createTracer();
      tracer.setCallGraphCache(callGraphFile);

      if (fromClass != null && toClass == null) {
        runForwardTrace(tracer);
      } else {
        runBackwardTrace(tracer);
      }
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }

  private void runForwardTrace(BytecodeTracer tracer) throws Exception {
    if (fromLine == null) {
      System.err.println("Forward trace requires --from <class> --from-line <line>");
      System.exit(1);
    }
    BytecodeTracer.FilterConfig filter = BytecodeTracer.FilterConfig.load(filterFile);
    Map<String, Object> result =
        new ForwardTracer(tracer).traceForward(fromClass, fromLine, filter);
    writeOutput(result);
  }

  private void runBackwardTrace(BytecodeTracer tracer) throws Exception {
    if (toClass == null || toLine == null) {
      System.err.println("Backward trace requires --to <class> --to-line <line>");
      System.exit(1);
    }
    String from = fromClass;
    int fLine = fromLine != null ? fromLine : -1;

    Map<String, Object> result =
        new BackwardTracer(tracer)
            .traceInterprocedural(from, fLine, toClass, toLine, maxDepth, collapse, flat);
    writeOutput(result);

    boolean found = (boolean) result.get("found");
    System.err.println("Found: " + found);
    if (found && collapse) {
      printCollapsedGroups(result);
    } else if (found) {
      printChains(result);
    }
  }

  @SuppressWarnings("unchecked")
  private void printCollapsedGroups(Map<String, Object> result) {
    List<Map<String, Object>> groups = (List<Map<String, Object>>) result.get("groups");
    System.err.println("Groups: " + groups.size());
    for (int i = 0; i < groups.size(); i++) {
      Map<String, Object> g = groups.get(i);
      System.err.println("Group " + (i + 1) + " (" + g.get("entryCount") + " entry points):");
      List<String> entries = (List<String>) g.get("entryPoints");
      for (String e : entries) {
        System.err.println("    ← " + e);
      }
      List<Map<String, Object>> chain = (List<Map<String, Object>>) g.get("chain");
      for (Map<String, Object> frame : chain) {
        String callSite =
            frame.containsKey("callSiteLine") ? " → L" + frame.get("callSiteLine") : "";
        System.err.println(
            "  "
                + frame.get("class")
                + "."
                + frame.get("method")
                + " L"
                + frame.get("lineStart")
                + "-"
                + frame.get("lineEnd")
                + " ("
                + frame.get("sourceLineCount")
                + " source lines)"
                + callSite);
      }
    }
  }

  @SuppressWarnings("unchecked")
  private void printChains(Map<String, Object> result) {
    List<List<Map<String, Object>>> chains = (List<List<Map<String, Object>>>) result.get("chains");
    System.err.println("Paths: " + chains.size());
    for (int i = 0; i < chains.size(); i++) {
      System.err.println("Chain " + (i + 1) + ":");
      for (Map<String, Object> frame : chains.get(i)) {
        String callSite =
            frame.containsKey("callSiteLine") ? " → L" + frame.get("callSiteLine") : "";
        System.err.println(
            "  "
                + frame.get("class")
                + "."
                + frame.get("method")
                + " L"
                + frame.get("lineStart")
                + "-"
                + frame.get("lineEnd")
                + " ("
                + frame.get("sourceLineCount")
                + " source lines)"
                + callSite);
      }
    }
  }
}
