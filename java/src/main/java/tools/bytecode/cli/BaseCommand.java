package tools.bytecode.cli;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import picocli.CommandLine.Option;
import picocli.CommandLine.ParentCommand;
import tools.bytecode.BytecodeTracer;

/** Shared setup for all subcommands — creates the tracer, handles --output. */
abstract class BaseCommand implements Runnable {

  @ParentCommand CLI parent;

  @Option(names = "--output", description = "Write JSON to file instead of stdout")
  Path output;

  final ObjectMapper mapper = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);

  BytecodeTracer createTracer() {
    System.err.println("[createTracer] classpath=" + parent.classpath);
    System.err.println("[createTracer] prefix=" + parent.prefix);
    BytecodeTracer tracer = new BytecodeTracer(parent.classpath);
    if (parent.prefix != null) tracer.setProjectPrefix(parent.prefix);
    System.err.println("[createTracer] tracer ready");
    return tracer;
  }

  void writeOutput(Map<String, Object> result) throws IOException {
    if (output != null) {
      Files.createDirectories(output.getParent());
      mapper.writeValue(output.toFile(), result);
      System.err.println("Output: " + output);
    } else {
      System.out.println(mapper.writeValueAsString(result));
    }
  }
}
