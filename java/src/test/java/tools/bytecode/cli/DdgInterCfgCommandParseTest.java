package tools.bytecode.cli;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import picocli.CommandLine;

class DdgInterCfgCommandParseTest {

  private static final String FAKE_CLASSPATH = "/tmp/fake";

  @Test
  void cliUsageListsDdgInterCfgSubcommand() {
    String usage = new CommandLine(new CLI()).getUsageMessage();
    assertTrue(usage.contains("ddg-inter-cfg"), usage);
  }

  @Test
  void acceptsNoInputOrOutputFlagsForPipeMode() {
    assertDoesNotThrow(() -> new CommandLine(new CLI()).parseArgs(FAKE_CLASSPATH, "ddg-inter-cfg"));
  }

  @Test
  void acceptsExplicitInputAndOutputFlags() {
    assertDoesNotThrow(
        () ->
            new CommandLine(new CLI())
                .parseArgs(
                    FAKE_CLASSPATH,
                    "ddg-inter-cfg",
                    "--input",
                    "/tmp/in.json",
                    "--output",
                    "/tmp/out.json"));
  }
}
