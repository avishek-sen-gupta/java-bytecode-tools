package tools.bytecode.cli;

import picocli.CommandLine;
import picocli.CommandLine.*;

@Command(
    name = "bytecode",
    mixinStandardHelpOptions = true,
    description = {
      "SootUp-based interprocedural bytecode analysis.",
      "",
      "Usage: bytecode [--prefix <pkg.>] <classpath> <subcommand> [options]",
      "",
      "  --prefix  Limit analysis to classes whose FQCN starts with this string.",
      "            Without it, every class visible on the classpath is analyzed.",
      "  classpath Colon-separated compiled .class directories or jars.",
      "",
      "Subcommands: buildcg  dump  xtrace",
      "",
      "JSON-producing commands write to stdout by default; use --output <file> to write a file.",
      "xtrace output can be piped into the Python post-processing tools:",
      "  ftrace-inter-slice | ftrace-intra-slice | ftrace-expand-refs | ftrace-semantic |"
          + " ftrace-to-dot",
      "  frames-print"
    },
    subcommands = {DumpCommand.class, BuildCgCommand.class, XtraceCommand.class})
public class CLI implements Runnable {

  @Option(
      names = "--prefix",
      description = "Limit analysis to classes whose FQCN starts with this prefix")
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
