package tools.source.icfg;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class StopConditionTest {

  @Test
  void exactMatchesOnlyThatFqn() {
    StopCondition sc = StopCondition.exact("java.lang.String");
    assertTrue(sc.test("java.lang.String"));
    assertFalse(sc.test("java.lang.Integer"));
    assertFalse(sc.test("java.lang.StringBuffer"));
  }

  @Test
  void prefixMatchesAnythingStartingWithNamespace() {
    StopCondition sc = StopCondition.prefix("java.");
    assertTrue(sc.test("java.lang.String"));
    assertTrue(sc.test("java.util.List"));
    assertFalse(sc.test("com.example.Foo"));
  }

  @Test
  void anyMatchesIfAnyConditionMatches() {
    StopCondition sc =
        StopCondition.any(
            StopCondition.exact("com.example.SpecialClass"), StopCondition.prefix("java."));
    assertTrue(sc.test("java.lang.String"));
    assertTrue(sc.test("com.example.SpecialClass"));
    assertFalse(sc.test("com.example.OtherClass"));
  }

  @Test
  void noneNeverMatches() {
    StopCondition sc = StopCondition.none();
    assertFalse(sc.test("java.lang.String"));
    assertFalse(sc.test("com.example.Anything"));
  }

  @Test
  void icfgConfigHoldsDepthAndCondition() {
    StopCondition sc = StopCondition.prefix("java.");
    IcfgConfig config = new IcfgConfig(3, sc);
    assertEquals(3, config.maxDepth());
    assertSame(sc, config.stopCondition());
  }
}
