package tools.source.icfg;

import static org.junit.jupiter.api.Assertions.*;

import fr.inria.controlflow.BranchKind;
import fr.inria.controlflow.ControlFlowGraph;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class SpoonMethodCfgCacheTest {

  private static SpoonMethodCfgCache cache;

  @BeforeAll
  static void buildCache() {
    cache = new SpoonMethodCfgCache("../test-fixtures/src");
  }

  @Test
  void buildsCfgForProcessOrder() {
    // processOrder is at line 16
    ControlFlowGraph cfg = cache.cfgFor("com.example.app.OrderService", 16);
    assertNotNull(cfg);
    assertTrue(cfg.vertexSet().size() > 0);
  }

  @Test
  void cfgHasBeginAndExitNodes() {
    ControlFlowGraph cfg = cache.cfgFor("com.example.app.OrderService", 16);
    long beginCount = cfg.vertexSet().stream().filter(n -> n.getKind() == BranchKind.BEGIN).count();
    long exitCount = cfg.vertexSet().stream().filter(n -> n.getKind() == BranchKind.EXIT).count();
    assertEquals(1, beginCount);
    assertEquals(1, exitCount);
  }

  @Test
  void cacheHitReturnsSameObject() {
    ControlFlowGraph first = cache.cfgFor("com.example.app.OrderService", 16);
    ControlFlowGraph second = cache.cfgFor("com.example.app.OrderService", 16);
    assertSame(first, second);
  }

  @Test
  void throwsForMethodNotFoundInClass() {
    assertThrows(
        IllegalArgumentException.class, () -> cache.cfgFor("com.example.app.OrderService", 5));
  }
}
