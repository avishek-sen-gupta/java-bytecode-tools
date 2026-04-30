package tools.source.icfg;

import static org.junit.jupiter.api.Assertions.*;

import fr.inria.controlflow.BranchKind;
import fr.inria.controlflow.ControlFlowNode;
import java.util.Set;
import org.junit.jupiter.api.Test;

class GraphTypesTest {

  @Test
  void icfgNodeExposesFields() {
    ControlFlowNode cfn = new ControlFlowNode(null, null, BranchKind.BEGIN);
    IcfgNode node = new IcfgNode(cfn, "com/example/Foo#bar().", 0);
    assertSame(cfn, node.cfgNode());
    assertEquals("com/example/Foo#bar().", node.methodSymbol());
    assertEquals(0, node.depth());
  }

  @Test
  void icfgNodeIdIsUniquePerDepthAndSymbolAndCfnId() {
    ControlFlowNode cfn1 = new ControlFlowNode(null, null, BranchKind.BEGIN);
    ControlFlowNode cfn2 = new ControlFlowNode(null, null, BranchKind.EXIT);
    IcfgNode a = new IcfgNode(cfn1, "A#m().", 0);
    IcfgNode b = new IcfgNode(cfn2, "A#m().", 0);
    assertNotEquals(a.id(), b.id());
  }

  @Test
  void icfgEdgeHoldsFromToKind() {
    ControlFlowNode cfn = new ControlFlowNode(null, null, BranchKind.BEGIN);
    IcfgNode n1 = new IcfgNode(cfn, "A#m().", 0);
    IcfgNode n2 = new IcfgNode(cfn, "B#x().", 1);
    IcfgEdge edge = new IcfgEdge(n1, n2, IcfgEdgeKind.CALL);
    assertSame(n1, edge.from());
    assertSame(n2, edge.to());
    assertEquals(IcfgEdgeKind.CALL, edge.kind());
  }

  @Test
  void interproceduralCfgExposesVerticesEdgesEntryExits() {
    ControlFlowNode cfnEntry = new ControlFlowNode(null, null, BranchKind.BEGIN);
    ControlFlowNode cfnExit = new ControlFlowNode(null, null, BranchKind.EXIT);
    IcfgNode entry = new IcfgNode(cfnEntry, "A#m().", 0);
    IcfgNode exit = new IcfgNode(cfnExit, "A#m().", 0);
    IcfgEdge edge = new IcfgEdge(entry, exit, IcfgEdgeKind.INTRA);
    InterproceduralCfg icfg =
        new InterproceduralCfg(Set.of(entry, exit), Set.of(edge), entry, Set.of(exit));
    assertEquals(2, icfg.vertexSet().size());
    assertEquals(1, icfg.edgeSet().size());
    assertSame(entry, icfg.entryNode());
    assertTrue(icfg.exitNodes().contains(exit));
  }
}
