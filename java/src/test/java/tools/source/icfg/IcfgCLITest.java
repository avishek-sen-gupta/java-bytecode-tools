package tools.source.icfg;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class IcfgCLITest {

  @Test
  void depth1ProducesValidDotFile(@TempDir Path tmp) throws Exception {
    Path dotOut = tmp.resolve("icfg.dot");
    int exit =
        IcfgCLI.run(
            new String[] {
              "--from", "com.example.app.OrderService",
              "--method", "processOrder",
              "--depth", "1",
              "--stop", "java.",
              "--index", "../test-fixtures/index.scip",
              "--source", "../test-fixtures/src",
              "--dot", dotOut.toString()
            });
    assertEquals(0, exit, "Expected exit code 0");
    assertTrue(Files.exists(dotOut), "DOT file should have been created");
    String content = Files.readString(dotOut);
    assertTrue(
        content.startsWith("digraph icfg {"),
        "DOT file content should start with 'digraph icfg {'");
  }

  @Test
  void depth0ProducesOnlyIntraEdges(@TempDir Path tmp) throws Exception {
    Path jsonOut = tmp.resolve("icfg.json");
    int exit =
        IcfgCLI.run(
            new String[] {
              "--from", "com.example.app.OrderService",
              "--method", "processOrder",
              "--depth", "0",
              "--index", "../test-fixtures/index.scip",
              "--source", "../test-fixtures/src",
              "--json", jsonOut.toString()
            });
    assertEquals(0, exit);
    String json = Files.readString(jsonOut);
    assertFalse(json.contains("\"CALL\""), "depth 0 should have no CALL edges");
  }

  @Test
  void missingRequiredFlagExitsNonZero() {
    int exit =
        IcfgCLI.run(
            new String[] {
              "--method", "processOrder",
              "--index", "../test-fixtures/index.scip",
              "--source", "../test-fixtures/src"
              // --from is missing
            });
    assertNotEquals(0, exit, "Missing --from should produce non-zero exit");
  }
}
