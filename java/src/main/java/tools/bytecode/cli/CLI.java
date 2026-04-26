package tools.bytecode.cli;

import picocli.CommandLine;
import picocli.CommandLine.*;

@Command(
    name = "bytecode",
    mixinStandardHelpOptions = true,
    description = "Bytecode analysis tools (SootUp).",
    subcommands = {
      DumpCommand.class, TraceCommand.class,
      BuildCgCommand.class, XtraceCommand.class
    })
public class CLI implements Runnable {

  @Option(names = "--prefix", description = "Filter classes by prefix")
  String prefix;

  @Parameters(index = "0", description = "Classpath (colon-separated directories/jars)")
  String classpath;

  @Override
  public void run() {
    CommandLine.usage(this, System.err);
  }

  public static void main(String[] args) {
    System.exit(new CommandLine(new CLI()).execute(args));
  }
}
