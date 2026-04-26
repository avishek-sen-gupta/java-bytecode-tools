package tools.bytecode.cli;

import java.util.List;
import java.util.Map;
import picocli.CommandLine.Command;
import picocli.CommandLine.Parameters;

@Command(
    name = "trace",
    mixinStandardHelpOptions = true,
    description = "Trace a path between two lines within a single method (intraprocedural).")
class TraceCommand extends BaseCommand {

  @Parameters(index = "0", description = "Fully qualified class name")
  String className;

  @Parameters(index = "1", description = "Source line to trace from")
  int fromLine;

  @Parameters(index = "2", description = "Source line to trace to")
  int toLine;

  @Override
  public void run() {
    try {
      var tracer = createTracer();
      Map<String, Object> result = tracer.trace(className, fromLine, toLine);
      writeOutput(result);

      @SuppressWarnings("unchecked")
      List<Map<String, Object>> traces = (List<Map<String, Object>>) result.get("traces");
      System.err.println("Traces found: " + traces.size());
      for (Map<String, Object> t : traces) {
        System.err.println(
            "  "
                + t.get("method")
                + ": "
                + t.get("stmtCount")
                + " stmts → "
                + t.get("sourceLineCount")
                + " source lines");
      }
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
}
