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
import tools.bytecode.artifact.DdgNode;
import tools.bytecode.artifact.LocalEdge;
import tools.bytecode.artifact.ParamEdge;
import tools.bytecode.artifact.ReturnEdge;

class DdgInterCfgArtifactBuilderTest {

  private static final String PROCESS_ORDER_SIG =
      "<com.example.app.OrderService: java.lang.String processOrder(int)>";
  private static final String REPO_FIND_BY_ID_SIG =
      "<com.example.app.OrderRepository: java.lang.String findById(int)>";
  private static final String JDBC_FIND_BY_ID_SIG =
      "<com.example.app.JdbcOrderRepository: java.lang.String findById(int)>";
  private static final String MISSING_SIG = "<com.example.app.MissingService: void nope()>";
  private static final String SANITIZE_SIG =
      "<com.example.app.VarReassignService: java.lang.String sanitize(java.lang.String)>";

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
  void ddgEdgeFromParamDefToReassignment() {
    // Reproduces the last-writer-wins bug in buildDdgEdges:
    // `value = value.replace(...)` must produce edge (identity_node → replace_node),
    // NOT a self-edge (replace_node → replace_node).
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                SANITIZE_SIG,
                Map.of(
                    "node_type", "java_method",
                    "class", "com.example.app.VarReassignService",
                    "method", "sanitize",
                    "methodSignature", SANITIZE_SIG)),
            "calls",
            List.of(),
            "metadata",
            Map.of("root", SANITIZE_SIG));

    DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer).build(input).ddg();

    // Find the IDENTITY node: "value := @parameter0: java.lang.String"
    // The fixture uses a conditional branch so SootUp emits non-SSA Jimple (unversioned
    // locals), matching the real-world pattern where the bug manifests.
    var identityNode =
        ddg.nodes().stream()
            .filter(n -> n.method().equals(SANITIZE_SIG))
            .filter(n -> n.stmt().contains(":= @parameter0"))
            .findFirst();

    if (identityNode.isEmpty()) {
      System.out.println("\n!!! Identity node not found. Available nodes:");
      ddg.nodes().stream()
          .filter(n -> n.method().equals(SANITIZE_SIG))
          .forEach(n -> System.out.println("  " + n.stmt()));
      throw new AssertionError("IDENTITY node for 'value' not found in DDG");
    }

    DdgNode identity = identityNode.get();

    // Find the replace() reassignment node: "value = virtualinvoke value.<...replace...>(...)"
    var replaceNodeOpt =
        ddg.nodes().stream()
            .filter(n -> n.method().equals(SANITIZE_SIG))
            .filter(n -> n.stmt().contains("replace") && n.stmt().contains(" = "))
            .findFirst();

    if (replaceNodeOpt.isEmpty()) {
      System.out.println("\n!!! Replace node not found. Available nodes:");
      ddg.nodes().stream()
          .filter(n -> n.method().equals(SANITIZE_SIG))
          .forEach(n -> System.out.println("  " + n.stmt()));
      throw new AssertionError("replace() reassignment node not found in DDG");
    }

    DdgNode replaceNode = replaceNodeOpt.get();

    // Assert: edge from IDENTITY → replace (the correct reaching-def edge)
    boolean hasCorrectEdge =
        ddg.edges().stream()
            .anyMatch(e -> e.from().equals(identity.id()) && e.to().equals(replaceNode.id()));

    assertTrue(
        hasCorrectEdge,
        "Expected LOCAL edge from IDENTITY node to replace() node: "
            + identity.id()
            + " -> "
            + replaceNode.id()
            + "\nActual edges from identity: "
            + ddg.edges().stream()
                .filter(e -> e.from().equals(identity.id()))
                .map(e -> e.to())
                .toList());

    // Assert: no self-edge on replace node
    boolean hasSelfEdge =
        ddg.edges().stream()
            .anyMatch(e -> e.from().equals(replaceNode.id()) && e.to().equals(replaceNode.id()));
    assertFalse(hasSelfEdge, "Unexpected self-edge on replace() node: " + replaceNode.id());
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

  @Test
  void ddgContainsParamAndReturnEdges() {
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                PROCESS_ORDER_SIG,
                Map.of(
                    "node_type", "java_method",
                    "class", "com.example.app.OrderService",
                    "method", "processOrder",
                    "methodSignature", PROCESS_ORDER_SIG)),
            "calls",
            List.of(),
            "metadata",
            Map.of("root", PROCESS_ORDER_SIG));

    // Single method — no inter-proc edges expected, but verify no crash
    DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer, null).build(input).ddg();

    // No calls → no PARAM/RETURN edges (but LOCAL edges should exist)
    long paramCount = ddg.edges().stream().filter(e -> e.edgeInfo() instanceof ParamEdge).count();
    long returnCount = ddg.edges().stream().filter(e -> e.edgeInfo() instanceof ReturnEdge).count();
    assertEquals(0, paramCount, "no calls → no PARAM edges");
    assertEquals(0, returnCount, "no calls → no RETURN edges");
    assertTrue(
        ddg.edges().stream().anyMatch(e -> e.edgeInfo() instanceof LocalEdge),
        "should still have LOCAL edges");
  }

  @Test
  void classifiesAssignInvokeWithSsaVersionedLocal() {
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                PROCESS_ORDER_SIG,
                Map.of(
                    "node_type", "java_method",
                    "class", "com.example.app.OrderService",
                    "method", "processOrder",
                    "methodSignature", PROCESS_ORDER_SIG)),
            "calls",
            List.of(),
            "metadata",
            Map.of("root", PROCESS_ORDER_SIG));

    DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer, null).build(input).ddg();

    var findByIdCallSites =
        ddg.nodes().stream()
            .filter(n -> n.method().equals(PROCESS_ORDER_SIG))
            .filter(n -> n.stmt().contains("findById"))
            .filter(n -> n.stmt().contains(" = "))
            .toList();

    assertFalse(findByIdCallSites.isEmpty(), "Should have at least one findById call site");

    for (DdgNode callSite : findByIdCallSites) {
      assertEquals(
          tools.bytecode.artifact.StmtKind.ASSIGN_INVOKE,
          callSite.kind(),
          "Call site should be ASSIGN_INVOKE, not INVOKE: " + callSite.stmt());
    }
  }

  @Test
  void interfaceDispatchGeneratesParamAndReturnEdges() {
    // OrderService.processOrder calls repo.findById(id) via OrderRepository interface.
    // Calltree resolves to JdbcOrderRepository (concrete).
    // Jimple call site will reference OrderRepository (interface).
    // Sub-signature matching should bridge the gap.
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                PROCESS_ORDER_SIG,
                Map.of(
                    "node_type", "java_method",
                    "class", "com.example.app.OrderService",
                    "method", "processOrder",
                    "methodSignature", PROCESS_ORDER_SIG),
                JDBC_FIND_BY_ID_SIG,
                Map.of(
                    "node_type", "java_method",
                    "class", "com.example.app.JdbcOrderRepository",
                    "method", "findById",
                    "methodSignature", JDBC_FIND_BY_ID_SIG)),
            "calls",
            List.of(Map.of("from", PROCESS_ORDER_SIG, "to", JDBC_FIND_BY_ID_SIG)),
            "metadata",
            Map.of("root", PROCESS_ORDER_SIG));

    DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer, null).build(input).ddg();

    long paramCount = ddg.edges().stream().filter(e -> e.edgeInfo() instanceof ParamEdge).count();
    long returnCount = ddg.edges().stream().filter(e -> e.edgeInfo() instanceof ReturnEdge).count();

    assertTrue(
        paramCount > 0,
        "Should have PARAM edges for interface-dispatched call. Nodes: "
            + ddg.nodes().stream()
                .filter(n -> n.stmt().contains("findById"))
                .map(n -> n.kind() + ": " + n.stmt())
                .toList());
    assertTrue(returnCount > 0, "Should have RETURN edges for interface-dispatched call");
  }

  @Test
  void castAssignmentToHashPrefixedLocalProducesLocalEdge() {
    // SootUp emits cast assignments as #l-prefixed locals:
    //   #l0 = (java.lang.CharSequence) "*"
    //   #l1 = (java.lang.CharSequence) "%"
    // These are then used as arguments in:
    //   value = virtualinvoke value.<...replace...>(#l0, #l1)
    //
    // Bug: the ASSIGN_LOCAL regex ^(\w[\w$#]*) requires the first character to be \w,
    // but # is not a word character. So #l0/#l1 definitions are never tracked in
    // reachingDef, and no LOCAL edge is created from the cast to the call-site use.
    // Similarly, extractLocalsFromExpr uses [a-z$] as first char, missing #l0 in the
    // RHS of the replace() call.
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                SANITIZE_SIG,
                Map.of(
                    "node_type", "java_method",
                    "class", "com.example.app.VarReassignService",
                    "method", "sanitize",
                    "methodSignature", SANITIZE_SIG)),
            "calls",
            List.of(),
            "metadata",
            Map.of("root", SANITIZE_SIG));

    DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer, null).build(input).ddg();

    // Find the cast assignment node: "#l0 = (java.lang.CharSequence) ..."
    var castNode =
        ddg.nodes().stream()
            .filter(n -> n.method().equals(SANITIZE_SIG))
            .filter(n -> n.stmt().startsWith("#l") && n.stmt().contains(" = "))
            .findFirst();

    assertTrue(castNode.isPresent(), "Should have a #l-prefixed cast assignment node");

    // Find the replace() call node that uses #l0/#l1 as arguments
    var replaceNode =
        ddg.nodes().stream()
            .filter(n -> n.method().equals(SANITIZE_SIG))
            .filter(n -> n.stmt().contains("replace") && n.stmt().contains("#l"))
            .findFirst();

    assertTrue(replaceNode.isPresent(), "Should have a replace() call using #l-prefixed args");

    // Assert: LOCAL edge from cast definition to the replace() call site
    boolean hasLocalEdge =
        ddg.edges().stream()
            .filter(e -> e.edgeInfo() instanceof LocalEdge)
            .anyMatch(
                e -> e.from().equals(castNode.get().id()) && e.to().equals(replaceNode.get().id()));

    assertTrue(
        hasLocalEdge,
        "Expected LOCAL edge from #l cast definition to replace() call: "
            + castNode.get().id()
            + " -> "
            + replaceNode.get().id()
            + "\nAll LOCAL edges: "
            + ddg.edges().stream()
                .filter(e -> e.edgeInfo() instanceof LocalEdge)
                .map(e -> e.from() + " -> " + e.to())
                .toList());
  }

  @Test
  void crossBlockReachingDefProducesLocalEdge() {
    // VarReassignService.sanitize has an if-branch that splits the CFG.
    // The parameter identity "value := @parameter0" must reach "return value"
    // even though they are in different basic blocks.
    // The current single-pass analysis fails this because it walks blocks linearly
    // and loses the reaching-def across the branch merge point.
    Map<String, Object> input =
        Map.of(
            "nodes",
            Map.of(
                SANITIZE_SIG,
                Map.of(
                    "node_type", "java_method",
                    "class", "com.example.app.VarReassignService",
                    "method", "sanitize",
                    "methodSignature", SANITIZE_SIG)),
            "calls",
            List.of(),
            "metadata",
            Map.of("root", SANITIZE_SIG));

    DdgGraph ddg = new DdgInterCfgArtifactBuilder(tracer, null).build(input).ddg();

    // Find the IDENTITY node: "value := @parameter0: java.lang.String"
    DdgNode identityNode =
        ddg.nodes().stream()
            .filter(n -> n.method().equals(SANITIZE_SIG))
            .filter(n -> n.stmt().contains(":= @parameter0"))
            .findFirst()
            .orElseThrow(() -> new AssertionError("IDENTITY node for 'value' not found"));

    // Find the return node: "return value"
    DdgNode returnNode =
        ddg.nodes().stream()
            .filter(n -> n.method().equals(SANITIZE_SIG))
            .filter(n -> n.stmt().startsWith("return "))
            .findFirst()
            .orElseThrow(() -> new AssertionError("RETURN node not found"));

    // Assert: LOCAL edge from identity → return (cross-block reaching-def)
    boolean hasEdge =
        ddg.edges().stream()
            .filter(e -> e.edgeInfo() instanceof LocalEdge)
            .anyMatch(e -> e.from().equals(identityNode.id()) && e.to().equals(returnNode.id()));

    assertTrue(
        hasEdge,
        "Expected cross-block LOCAL edge from IDENTITY to RETURN: "
            + identityNode.id()
            + " -> "
            + returnNode.id()
            + "\nAll LOCAL edges: "
            + ddg.edges().stream()
                .filter(e -> e.edgeInfo() instanceof LocalEdge)
                .map(e -> e.from() + " -> " + e.to())
                .toList());
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
