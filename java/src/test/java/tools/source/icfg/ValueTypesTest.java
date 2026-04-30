package tools.source.icfg;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ValueTypesTest {

  @Test
  void sourceLocationHoldsFileAndLines() {
    SourceLocation loc = new SourceLocation("com/example/app/Foo.java", 10, 20);
    assertEquals("com/example/app/Foo.java", loc.file());
    assertEquals(10, loc.startLine());
    assertEquals(20, loc.endLine());
  }

  @Test
  void icfgEdgeKindHasThreeValues() {
    assertEquals(3, IcfgEdgeKind.values().length);
    assertNotNull(IcfgEdgeKind.INTRA);
    assertNotNull(IcfgEdgeKind.CALL);
    assertNotNull(IcfgEdgeKind.RETURN);
  }
}
