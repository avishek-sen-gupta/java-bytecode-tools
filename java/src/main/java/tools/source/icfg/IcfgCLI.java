package tools.source.icfg;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import picocli.CommandLine;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;

@Command(
    name = "icfg",
    mixinStandardHelpOptions = true,
    description = "Build an interprocedural CFG using Spoon + SCIP cross-references.")
public class IcfgCLI implements Runnable {

  @Option(names = "--from", required = true, description = "Entry class FQN")
  String fromClass;

  @Option(names = "--method", required = true, description = "Entry method name")
  String methodName;

  @Option(names = "--depth", defaultValue = "3", description = "Max expansion depth (default 3)")
  int maxDepth;

  @Option(names = "--stop", description = "Namespace prefix stop condition (repeatable)")
  List<String> stopPrefixes = new ArrayList<>();

  @Option(names = "--stop-exact", description = "Exact FQN stop condition (repeatable)")
  List<String> stopExact = new ArrayList<>();

  @Option(names = "--index", required = true, description = "Path to index.scip")
  Path indexPath;

  @Option(names = "--source", required = true, description = "Path to source root")
  String sourceRoot;

  @Option(names = "--dot", description = "Write DOT output to this file")
  Path dotOutput;

  @Option(names = "--svg", description = "Write SVG output to this file (requires Graphviz)")
  Path svgOutput;

  @Option(names = "--json", description = "Write JSON output to this file")
  Path jsonOutput;

  private int exitCode = 0;

  @Override
  public void run() {
    try {
      StopCondition stop = buildStopCondition();
      IcfgConfig config = new IcfgConfig(maxDepth, stop);
      ScipIndex index = new ScipIndex(indexPath);
      SpoonMethodCfgCache cache = new SpoonMethodCfgCache(sourceRoot);
      InterproceduralCfg icfg =
          new IcfgBuilder().build(fromClass, methodName, index, cache, config);

      if (dotOutput != null || svgOutput != null) {
        String dot = new IcfgDotExporter().toDot(icfg);
        if (dotOutput != null) {
          Files.writeString(dotOutput, dot);
        }
        if (svgOutput != null) {
          writeSvg(dot, svgOutput);
        }
      }
      if (jsonOutput != null) {
        Files.writeString(jsonOutput, new IcfgJsonExporter().toJson(icfg));
      }
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      e.printStackTrace(System.err);
      exitCode = 1;
    }
  }

  private StopCondition buildStopCondition() {
    List<StopCondition> conditions = new ArrayList<>();
    stopPrefixes.forEach(p -> conditions.add(StopCondition.prefix(p)));
    stopExact.forEach(f -> conditions.add(StopCondition.exact(f)));
    return conditions.isEmpty()
        ? StopCondition.none()
        : StopCondition.any(conditions.toArray(StopCondition[]::new));
  }

  private void writeSvg(String dot, Path svgPath) throws IOException, InterruptedException {
    Path tmpDot = Files.createTempFile("icfg-", ".dot");
    try {
      Files.writeString(tmpDot, dot);
      ProcessBuilder pb =
          new ProcessBuilder("dot", "-Tsvg", "-o", svgPath.toString(), tmpDot.toString());
      pb.redirectErrorStream(true);
      Process p = pb.start();
      int exit = p.waitFor();
      if (exit != 0) {
        String out = new String(p.getInputStream().readAllBytes());
        throw new IOException("[dot failed exit=" + exit + "]: " + out);
      }
    } finally {
      Files.deleteIfExists(tmpDot);
    }
  }

  /** Entry point for tests — returns exit code. */
  public static int run(String[] args) {
    IcfgCLI cmd = new IcfgCLI();
    int code = new CommandLine(cmd).execute(args);
    return code != 0 ? code : cmd.exitCode;
  }

  public static void main(String[] args) {
    System.exit(run(args));
  }
}
