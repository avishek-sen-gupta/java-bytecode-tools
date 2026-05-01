package tools.bytecode.artifact;

import java.util.List;

public record CalltreeGraph(List<CalltreeNode> nodes, List<CalltreeEdge> edges) {}
