package tools.bytecode.artifact;

import com.fasterxml.jackson.annotation.JsonCreator;

public record ParamEdge() implements EdgeInfo {
  @JsonCreator
  public ParamEdge {}
}
