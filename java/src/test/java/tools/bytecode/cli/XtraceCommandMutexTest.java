package tools.bytecode.cli;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import picocli.CommandLine;
import picocli.CommandLine.ParameterException;

class XtraceCommandMutexTest {

  private static final String FAKE_CLASSPATH = "/tmp/fake";

  private void parseArgs(String... args) {
    new CommandLine(new CLI()).parseArgs(args);
  }

  @Test
  void rejectsNeitherFromLineNorFromMethod() {
    assertThrows(
        ParameterException.class,
        () ->
            parseArgs(
                FAKE_CLASSPATH,
                "xtrace",
                "--from",
                "com.example.Foo",
                "--call-graph",
                "/tmp/cg.json"),
        "Should reject when neither --from-line nor --from-method given");
  }

  @Test
  void rejectsBothFromLineAndFromMethod() {
    assertThrows(
        ParameterException.class,
        () ->
            parseArgs(
                FAKE_CLASSPATH,
                "xtrace",
                "--from",
                "com.example.Foo",
                "--from-line",
                "10",
                "--from-method",
                "bar",
                "--call-graph",
                "/tmp/cg.json"),
        "Should reject when both --from-line and --from-method given");
  }

  @Test
  void acceptsFromLineAlone() {
    assertDoesNotThrow(
        () ->
            parseArgs(
                FAKE_CLASSPATH,
                "xtrace",
                "--from",
                "com.example.Foo",
                "--from-line",
                "10",
                "--call-graph",
                "/tmp/cg.json"),
        "Should accept when --from-line alone given");
  }

  @Test
  void acceptsFromMethodAlone() {
    assertDoesNotThrow(
        () ->
            parseArgs(
                FAKE_CLASSPATH,
                "xtrace",
                "--from",
                "com.example.Foo",
                "--from-method",
                "bar",
                "--call-graph",
                "/tmp/cg.json"),
        "Should accept when --from-method alone given");
  }
}
