package tools.bytecode.cli;

import java.nio.file.Path;
import java.util.Map;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import tools.bytecode.BackwardTracer;

@Command(
    name = "frames",
    mixinStandardHelpOptions = true,
    description =
        "Backward interprocedural trace — find all call chains reaching a target method."
            + " Output is a lightweight nested frame tree (no CFG data).")
class FramesCommand extends BaseCommand {

  @Option(
      names = "--to",
      required = true,
      description = "Target class (the method you want to find callers for)")
  String toClass;

  @Option(names = "--to-line", required = true, description = "Source line in --to class")
  int toLine;

  @Option(names = "--from", description = "Constrain to a specific entry-point class")
  String fromClass;

  @Option(names = "--from-line", description = "Source line in --from class")
  Integer fromLine;

  @Option(names = "--depth", description = "Max backward BFS depth", defaultValue = "50")
  int maxDepth;

  @Option(names = "--call-graph", required = true, description = "Path to call graph JSON file")
  Path callGraphFile;

  @Override
  public void run() {
    if (fromClass != null && fromLine == null) {
      System.err.println("--from requires --from-line");
      System.exit(1);
    }
    try {
      var tracer = createTracer();
      tracer.setCallGraphCache(callGraphFile);
      int fLine = fromLine != null ? fromLine : -1;
      Map<String, Object> result =
          new BackwardTracer(tracer)
              .traceInterprocedural(fromClass, fLine, toClass, toLine, maxDepth);
      writeOutput(result);

      boolean found = Boolean.TRUE.equals(result.get("found"));
      System.err.println("Found: " + found);
      if (found) {
        @SuppressWarnings("unchecked")
        java.util.List<Map<String, Object>> chains =
            (java.util.List<Map<String, Object>>)
                ((Map<String, Object>) result.get("trace")).get("children");
        System.err.println("Chains: " + chains.size());
      }
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
}
