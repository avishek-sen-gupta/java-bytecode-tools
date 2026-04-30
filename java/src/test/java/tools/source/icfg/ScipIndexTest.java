package tools.source.icfg;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Path;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class ScipIndexTest {

  private static ScipIndex index;

  @BeforeAll
  static void loadIndex() throws Exception {
    index = new ScipIndex(Path.of("../test-fixtures/index.scip"));
  }

  @Test
  void resolvesOrderRepositoryFindById() {
    SourceLocation loc = index.locationOf("com.example.app.OrderRepository", "findById");
    assertTrue(
        loc.file().endsWith("OrderRepository.java"),
        "Expected file ending in OrderRepository.java but got: " + loc.file());
    assertEquals(5, loc.startLine());
  }

  @Test
  void resolvesOrderRepositorySave() {
    SourceLocation loc = index.locationOf("com.example.app.OrderRepository", "save");
    assertTrue(loc.file().endsWith("OrderRepository.java"));
    assertEquals(6, loc.startLine());
  }

  @Test
  void resolvesOrderServiceProcessOrder() {
    SourceLocation loc = index.locationOf("com.example.app.OrderService", "processOrder");
    assertTrue(loc.file().endsWith("OrderService.java"));
    assertEquals(16, loc.startLine());
  }

  @Test
  void throwsForUnknownMethod() {
    assertThrows(
        IllegalArgumentException.class,
        () -> index.locationOf("com.example.app.OrderRepository", "nonExistentMethod"));
  }

  @Test
  void hasDefinitionReturnsTrueForKnownMethod() {
    assertTrue(index.hasDefinition("com.example.app.OrderRepository", "findById"));
  }

  @Test
  void hasDefinitionReturnsFalseForUnknownMethod() {
    assertFalse(index.hasDefinition("com.example.app.OrderRepository", "nonExistentMethod"));
  }
}
