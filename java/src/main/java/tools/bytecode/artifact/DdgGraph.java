package tools.bytecode.artifact;

import java.util.List;

public record DdgGraph(List<DdgNode> nodes, List<DdgEdge> edges) {}
