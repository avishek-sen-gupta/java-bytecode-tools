package tools.bytecode.artifact;

public record HeapEdge(String field) implements EdgeInfo {
  @Override
  public String kindName() {
    return "HEAP";
  }
}
