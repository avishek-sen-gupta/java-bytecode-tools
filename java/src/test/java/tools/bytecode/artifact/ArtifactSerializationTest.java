package tools.bytecode.artifact;

import static org.junit.jupiter.api.Assertions.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ArtifactSerializationTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Test
  void roundTripArtifactWithAllEdgeKinds() throws Exception {
    Artifact original =
        new Artifact(
            Map.of("root", "<com.example.Foo: void bar()>"),
            new CalltreeGraph(
                List.of(new CalltreeNode("<com.example.Foo: void bar()>", "Foo", "bar")),
                List.of(
                    new CalltreeEdge(
                        "<com.example.Caller: void main()>", "<com.example.Foo: void bar()>"))),
            new DdgGraph(
                List.of(
                    new DdgNode(
                        "<com.example.Foo: void bar()>#s0",
                        "<com.example.Foo: void bar()>",
                        "s0",
                        "i0 := @parameter0: int",
                        -1,
                        StmtKind.IDENTITY,
                        Map.of())),
                List.of(
                    new DdgEdge(
                        "<com.example.Foo: void bar()>#s0",
                        "<com.example.Foo: void bar()>#s1",
                        new LocalEdge()),
                    new DdgEdge(
                        "<com.example.A: void set()>#s2",
                        "<com.example.B: void get()>#s3",
                        new HeapEdge("<com.example.A: int count>")),
                    new DdgEdge("sigA#s4", "sigB#s5", new ParamEdge()),
                    new DdgEdge("sigA#s6", "sigB#s7", new ReturnEdge()))));

    String json = MAPPER.writeValueAsString(original);
    Artifact deserialized = MAPPER.readValue(json, Artifact.class);

    assertEquals(original.metadata(), deserialized.metadata());
    assertEquals(1, deserialized.calltree().nodes().size());
    assertEquals(1, deserialized.calltree().edges().size());
    assertEquals(1, deserialized.ddg().nodes().size());
    assertEquals(4, deserialized.ddg().edges().size());

    // Verify edge kind polymorphism
    assertInstanceOf(LocalEdge.class, deserialized.ddg().edges().get(0).edgeInfo());
    HeapEdge heapEdge =
        assertInstanceOf(HeapEdge.class, deserialized.ddg().edges().get(1).edgeInfo());
    assertEquals("<com.example.A: int count>", heapEdge.field());
    assertInstanceOf(ParamEdge.class, deserialized.ddg().edges().get(2).edgeInfo());
    assertInstanceOf(ReturnEdge.class, deserialized.ddg().edges().get(3).edgeInfo());
  }

  @Test
  void edgeInfoJsonContainsKindField() throws Exception {
    DdgEdge localEdge = new DdgEdge("a#s0", "a#s1", new LocalEdge());
    DdgEdge heapEdge = new DdgEdge("a#s2", "b#s3", new HeapEdge("<Foo: int f>"));

    String localJson = MAPPER.writeValueAsString(localEdge);
    String heapJson = MAPPER.writeValueAsString(heapEdge);

    assertTrue(localJson.contains("\"kind\":\"LOCAL\""), "LOCAL edge_info must contain kind=LOCAL");
    assertTrue(heapJson.contains("\"kind\":\"HEAP\""), "HEAP edge_info must contain kind=HEAP");
    assertTrue(
        heapJson.contains("\"field\":\"<Foo: int f>\""), "HEAP edge_info must contain field");
  }
}
