package tools.source.icfg;

import java.util.Set;

public record InterproceduralCfg(
    Set<IcfgNode> vertexSet, Set<IcfgEdge> edgeSet, IcfgNode entryNode, Set<IcfgNode> exitNodes) {}
