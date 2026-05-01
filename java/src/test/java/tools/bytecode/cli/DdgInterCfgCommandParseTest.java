package tools.bytecode.cli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import picocli.CommandLine;
import picocli.CommandLine.ParseResult;

class DdgInterCfgCommandParseTest {

  private static final String FAKE_CLASSPATH = "/tmp/fake";

  private static DdgInterCfgCommand parsedCommand(String... args) {
    ParseResult parseResult = new CommandLine(new CLI()).parseArgs(args);
    return (DdgInterCfgCommand) parseResult.subcommand().commandSpec().userObject();
  }

  @Test
  void cliUsageListsDdgInterCfgSubcommand() {
    String usage = new CommandLine(new CLI()).getUsageMessage();
    assertTrue(usage.contains("ddg-inter-cfg"), usage);
  }

  @Test
  void acceptsNoInputOrOutputFlagsForPipeMode() {
    DdgInterCfgCommand command = parsedCommand(FAKE_CLASSPATH, "ddg-inter-cfg");
    assertNull(command.input);
    assertNull(command.output);
  }

  @Test
  void acceptsExplicitInputAndOutputFlags() {
    DdgInterCfgCommand command =
        parsedCommand(
            FAKE_CLASSPATH,
            "ddg-inter-cfg",
            "--input",
            "/tmp/in.json",
            "--output",
            "/tmp/out.json");
    assertEquals(Path.of("/tmp/in.json"), command.input);
    assertEquals(Path.of("/tmp/out.json"), command.output);
  }
}
