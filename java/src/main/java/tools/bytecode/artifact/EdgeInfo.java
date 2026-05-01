package tools.bytecode.artifact;

import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(use = JsonTypeInfo.Id.NAME, property = "kind")
@JsonSubTypes({
  @JsonSubTypes.Type(value = LocalEdge.class, name = "LOCAL"),
  @JsonSubTypes.Type(value = HeapEdge.class, name = "HEAP"),
  @JsonSubTypes.Type(value = ParamEdge.class, name = "PARAM"),
  @JsonSubTypes.Type(value = ReturnEdge.class, name = "RETURN")
})
public sealed interface EdgeInfo permits LocalEdge, HeapEdge, ParamEdge, ReturnEdge {}
