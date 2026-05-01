package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Paths;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.bytecode.artifact.Artifact;
import tools.bytecode.artifact.DdgGraph;

class DdgInterCfgArtifactBuilderTest {

  private static final String PROCESS_ORDER_SIG =
      "<com.example.app.OrderService: java.lang.String processOrder(int)>";
  private static final String REPO_FIND_BY_ID_SIG =
      "<com.example.app.OrderRepository: java.lang.String findById(int)>";
  private static final String MISSING_SIG = "<com.example.app.MissingService: void nope()>";

  private static BytecodeTracer tracer;

  @BeforeAll
  static void setUp() {
    String classpath = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    tracer = new BytecodeTracer(classpath, "com.example.app", null);
  }

  @Test
  void preservesNodesAndCallsAndBuildsArtifact() {
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                PROCESS_ORDER_SIG,
                Map.of(
                    "node_type",
                    "java_method",
                    "class",
                    "com.example.app.OrderService",
                    "method",
                    "processOrder",
                    "methodSignature",
                    PROCESS_ORDER_SIG)),
            "calls",
            List.of(),
            "metadata",
            Map.of("root", PROCESS_ORDER_SIG));

    Artifact artifact = new DdgInterCfgArtifactBuilder(tracer).build(input);

    assertNotNull(artifact, "Artifact should not be null");
    assertNotNull(artifact.calltree(), "Calltree should not be null");
    assertNotNull(artifact.ddg(), "DDG should not be null");
    assertEquals(
        PROCESS_ORDER_SIG,
        artifact.metadata().get("root"),
        "Metadata should preserve root from input");
    assertTrue(
        artifact.calltree().nodes().stream().anyMatch(n -> n.id().equals(PROCESS_ORDER_SIG)),
        "Calltree should contain root method");
  }

  @Test
  void rejectsMissingNodes() {
    IllegalArgumentException ex =
        assertThrows(
            IllegalArgumentException.class,
            () -> new DdgInterCfgArtifactBuilder(tracer).build(Map.of("calls", List.of())));
    assertTrue(ex.getMessage().contains("nodes"), ex.getMessage());
  }

  @Test
  void rejectsEmptyNodes() {
    IllegalArgumentException ex =
        assertThrows(
            IllegalArgumentException.class,
            () -> new DdgInterCfgArtifactBuilder(tracer).build(Map.of("nodes", Map.of())));
    assertTrue(ex.getMessage().contains("nodes"), ex.getMessage());
  }

  @Test
  void rejectsResolvedMethodWithoutBody() {
    IllegalArgumentException ex =
        assertThrows(
            IllegalArgumentException.class,
            () ->
                new DdgInterCfgArtifactBuilder(tracer)
                    .build(
                        Map.of(
                            "nodes",
                            Map.of(
                                REPO_FIND_BY_ID_SIG,
                                Map.of("methodSignature", REPO_FIND_BY_ID_SIG)))));
    assertTrue(ex.getMessage().contains("has no body"), ex.getMessage());
    assertTrue(ex.getMessage().contains(REPO_FIND_BY_ID_SIG), ex.getMessage());
  }

  @Test
  void rejectsUnresolvedMethodSignature() {
    RuntimeException ex =
        assertThrows(
            RuntimeException.class,
            () ->
                new DdgInterCfgArtifactBuilder(tracer)
                    .build(
                        Map.of(
                            "nodes", Map.of(MISSING_SIG, Map.of("methodSignature", MISSING_SIG)))));
    assertTrue(ex.getMessage().contains("Method not found"), ex.getMessage());
    assertTrue(ex.getMessage().contains(MISSING_SIG), ex.getMessage());
  }

  @Test
  void enricherIsAppliedToRawDdg() {
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                PROCESS_ORDER_SIG,
                Map.of(
                    "node_type",
                    "java_method",
                    "class",
                    "com.example.app.OrderService",
                    "method",
                    "processOrder",
                    "methodSignature",
                    PROCESS_ORDER_SIG)),
            "calls",
            List.of(),
            "metadata",
            Map.of("root", PROCESS_ORDER_SIG));

    // Use a test enricher that records the inScopeMethodSigs
    TestFieldDepEnricher testEnricher = new TestFieldDepEnricher();
    Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, testEnricher).build(input);

    assertNotNull(artifact, "Artifact should not be null");
    assertNotNull(testEnricher.capturedScope, "Enricher should be called with inScopeMethodSigs");
    assertTrue(
        testEnricher.capturedScope.contains(PROCESS_ORDER_SIG),
        "Enricher should receive PROCESS_ORDER_SIG in scope");
  }

  @Test
  void nullEnricherLeavesRawDdg() {
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                PROCESS_ORDER_SIG,
                Map.of(
                    "node_type",
                    "java_method",
                    "class",
                    "com.example.app.OrderService",
                    "method",
                    "processOrder",
                    "methodSignature",
                    PROCESS_ORDER_SIG)),
            "calls",
            List.of(),
            "metadata",
            Map.of("root", PROCESS_ORDER_SIG));

    Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, null).build(input);

    assertNotNull(artifact, "Artifact should not be null");
    assertNotNull(artifact.ddg(), "DDG should not be null");
    // With null enricher and single method with simple body, DDG should have some nodes
    assertTrue(!artifact.ddg().nodes().isEmpty(), "DDG should have nodes from raw build");
  }

  // Test helper: records the inScopeMethodSigs passed to enrich()
  static class TestFieldDepEnricher extends FieldDepEnricher {
    Set<String> capturedScope = null;

    TestFieldDepEnricher() {
      super((a, b, c, d) -> false);
    }

    @Override
    public DdgGraph enrich(DdgGraph ddg, Set<String> inScope) {
      capturedScope = inScope;
      return ddg; // pass-through
    }
  }
}
