package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Paths;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import sootup.analysis.intraprocedural.reachingdefs.ReachingDefs;
import sootup.codepropertygraph.ddg.DdgCreator;
import sootup.codepropertygraph.propertygraph.PropertyGraph;
import sootup.codepropertygraph.propertygraph.edges.DdgEdge;
import sootup.codepropertygraph.propertygraph.edges.PropertyGraphEdge;
import sootup.codepropertygraph.propertygraph.nodes.StmtGraphNode;
import sootup.core.jimple.common.stmt.JIfStmt;
import sootup.core.jimple.common.stmt.JReturnStmt;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.SootMethod;

class SootUpDataDependencyExperimentTest {

  private static final String CLASSPATH =
      Paths.get("../test-fixtures/classes").toAbsolutePath().toString();

  private static BytecodeTracer tracer;

  @BeforeAll
  static void setUp() {
    tracer = new BytecodeTracer(CLASSPATH);
    tracer.setProjectPrefix("com.example.app");
  }

  @Test
  void reachingDefinitionsExposeDependenciesIntoBranchesAndReturns() {
    SootMethod method = tracer.resolveMethodByName("com.example.app.OrderService", "processOrder");
    ReachingDefs reachingDefs = new ReachingDefs(method.getBody().getStmtGraph());

    Map<Stmt, List<Stmt>> defsByUse = reachingDefs.getReachingDefs();

    assertFalse(defsByUse.isEmpty(), "Expected reaching-def results for processOrder");
    assertTrue(
        defsByUse.entrySet().stream()
            .anyMatch(entry -> entry.getKey() instanceof JIfStmt && !entry.getValue().isEmpty()),
        () -> "Expected reaching defs for a branch condition, got: " + summarize(defsByUse));
    assertTrue(
        defsByUse.entrySet().stream()
            .anyMatch(
                entry -> entry.getKey() instanceof JReturnStmt && !entry.getValue().isEmpty()),
        () -> "Expected reaching defs for a return statement, got: " + summarize(defsByUse));
  }

  @Test
  void ddgCreatorBuildsEdgesForControlAndReturnUses() {
    SootMethod method = tracer.resolveMethodByName("com.example.app.OrderService", "processOrder");
    PropertyGraph ddg = new DdgCreator().createGraph(method);

    List<DdgEdge> ddgEdges =
        ddg.getEdges().stream()
            .filter(DdgEdge.class::isInstance)
            .map(DdgEdge.class::cast)
            .collect(Collectors.toList());

    assertFalse(ddg.getNodes().isEmpty(), "Expected DDG nodes");
    assertFalse(ddgEdges.isEmpty(), "Expected at least one DDG edge");
    assertTrue(
        ddgEdges.stream().allMatch(edge -> "ddg_next".equals(edge.getLabel())),
        () -> "Unexpected DDG edge labels: " + summarizeEdges(ddgEdges));
    assertTrue(
        ddgEdges.stream().anyMatch(edge -> destinationStmt(edge) instanceof JIfStmt),
        () -> "Expected a DDG edge into a branch statement, got: " + summarizeEdges(ddgEdges));
    assertTrue(
        ddgEdges.stream().anyMatch(edge -> destinationStmt(edge) instanceof JReturnStmt),
        () -> "Expected a DDG edge into a return statement, got: " + summarizeEdges(ddgEdges));
  }

  private static Stmt destinationStmt(PropertyGraphEdge edge) {
    assertInstanceOf(StmtGraphNode.class, edge.getDestination(), "Expected stmt-backed DDG node");
    return ((StmtGraphNode) edge.getDestination()).getStmt();
  }

  private static String summarize(Map<Stmt, List<Stmt>> defsByUse) {
    return defsByUse.entrySet().stream()
        .map(
            entry ->
                entry.getKey()
                    + " <= "
                    + entry.getValue().stream()
                        .map(Object::toString)
                        .collect(Collectors.joining(", ")))
        .collect(Collectors.joining(" | "));
  }

  private static String summarizeEdges(List<DdgEdge> edges) {
    return edges.stream()
        .map(edge -> edge.getSource() + " -[" + edge.getLabel() + "]-> " + edge.getDestination())
        .collect(Collectors.joining(" | "));
  }
}
