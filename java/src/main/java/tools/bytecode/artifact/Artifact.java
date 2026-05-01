package tools.bytecode.artifact;

import java.util.Map;

public record Artifact(Map<String, String> metadata, CalltreeGraph calltree, DdgGraph ddg) {}
