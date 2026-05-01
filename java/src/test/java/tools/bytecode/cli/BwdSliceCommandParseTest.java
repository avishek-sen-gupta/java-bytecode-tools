package tools.bytecode.cli;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import picocli.CommandLine;
import picocli.CommandLine.ParseResult;

class BwdSliceCommandParseTest {

  private static final String FAKE_CLASSPATH = "/tmp/fake";
  private static final String FAKE_METHOD = "<com.example.Foo: void bar()>";

  private static BwdSliceCommand parsedCommand(String... args) {
    ParseResult parseResult = new CommandLine(new CLI()).parseArgs(args);
    return (BwdSliceCommand) parseResult.subcommand().commandSpec().userObject();
  }

  @Test
  void cliUsageListsBwdSliceSubcommand() {
    String usage = new CommandLine(new CLI()).getUsageMessage();
    assertTrue(usage.contains("bwd-slice"), usage);
  }

  @Test
  void acceptsNoInputFlagForPipeMode() {
    BwdSliceCommand cmd =
        parsedCommand(FAKE_CLASSPATH, "bwd-slice", "--method", FAKE_METHOD, "--local-var", "r0");
    assertNull(cmd.input);
    assertEquals(FAKE_METHOD, cmd.method);
    assertEquals("r0", cmd.localVar);
  }

  @Test
  void acceptsExplicitInputFlag() {
    BwdSliceCommand cmd =
        parsedCommand(
            FAKE_CLASSPATH,
            "bwd-slice",
            "--input",
            "/tmp/artifact.json",
            "--method",
            FAKE_METHOD,
            "--local-var",
            "r1");
    assertEquals(Path.of("/tmp/artifact.json"), cmd.input);
  }
}
