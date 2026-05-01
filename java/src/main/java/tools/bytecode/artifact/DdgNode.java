package tools.bytecode.artifact;

import java.util.Map;

public record DdgNode(
    String id,
    String method,
    String stmtId,
    String stmt,
    int line,
    StmtKind kind,
    Map<String, String> call) {}
