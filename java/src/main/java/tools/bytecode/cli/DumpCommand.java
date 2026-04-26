package tools.bytecode.cli;

import java.util.Map;
import picocli.CommandLine.Command;
import picocli.CommandLine.Parameters;

@Command(
    name = "dump",
    mixinStandardHelpOptions = true,
    description = "Show all methods in a class with their source line ranges.")
class DumpCommand extends BaseCommand {

  @Parameters(index = "0", description = "Fully qualified class name")
  String className;

  @Override
  public void run() {
    try {
      var tracer = createTracer();
      Map<String, Object> result = tracer.dumpLineMap(className);
      writeOutput(result);
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
}
