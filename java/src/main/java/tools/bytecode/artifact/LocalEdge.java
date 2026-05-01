package tools.bytecode.artifact;

import com.fasterxml.jackson.annotation.JsonCreator;

public record LocalEdge() implements EdgeInfo {
  @JsonCreator
  public LocalEdge {}
}
