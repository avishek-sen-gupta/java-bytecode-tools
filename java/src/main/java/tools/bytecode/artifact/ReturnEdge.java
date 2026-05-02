package tools.bytecode.artifact;

import com.fasterxml.jackson.annotation.JsonCreator;

public record ReturnEdge() implements EdgeInfo {
  @JsonCreator
  public ReturnEdge {}

  @Override
  public String kindName() {
    return "RETURN";
  }
}
