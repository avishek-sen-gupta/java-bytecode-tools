package tools.source.icfg;

import fr.inria.controlflow.ControlFlowNode;

public record IcfgNode(ControlFlowNode cfgNode, String methodSymbol, int depth) {
  public String id() {
    return depth + "_" + Math.abs(methodSymbol.hashCode()) + "_" + cfgNode.getId();
  }
}
