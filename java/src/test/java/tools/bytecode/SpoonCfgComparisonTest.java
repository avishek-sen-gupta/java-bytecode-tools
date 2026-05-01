package tools.bytecode;

import fr.inria.controlflow.BranchKind;
import fr.inria.controlflow.ControlFlowBuilder;
import fr.inria.controlflow.ControlFlowEdge;
import fr.inria.controlflow.ControlFlowGraph;
import fr.inria.controlflow.ControlFlowNode;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;
import sootup.core.graph.StmtGraph;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.SootMethod;
import spoon.Launcher;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.code.CtVariableAccess;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.visitor.filter.TypeFilter;

class SpoonCfgComparisonTest {

  private static final String CLASSPATH = "../test-fixtures/classes";
  private static final String SOURCE_PATH = "../test-fixtures/src";
  private static final String CLASS_NAME = "com.example.app.OrderService";
  private static final String METHOD_NAME = "processOrder";

  @Test
  void compareCfgs() throws Exception {
    // ----------------------------------------------------------------
    // SootUp side
    // ----------------------------------------------------------------
    BytecodeTracer tracer = new BytecodeTracer(CLASSPATH, "", null);
    SootMethod sootMethod = tracer.resolveMethodByName(CLASS_NAME, METHOD_NAME);
    StmtGraph<?> stmtGraph = sootMethod.getBody().getStmtGraph();
    List<Stmt> sootNodes = new ArrayList<>(stmtGraph.getNodes());

    System.out.println("\n=== SOOTUP CFG NODES ===");
    for (int i = 0; i < sootNodes.size(); i++) {
      Stmt s = sootNodes.get(i);
      System.out.printf("  [n%d, line %3d] %s%n", i, StmtAnalyzer.stmtLine(s), s);
    }

    System.out.println("\n=== SOOTUP CFG EDGES ===");
    for (int i = 0; i < sootNodes.size(); i++) {
      for (Stmt dst : stmtGraph.successors(sootNodes.get(i))) {
        System.out.printf("  n%d -> n%d%n", i, sootNodes.indexOf(dst));
      }
    }

    // ----------------------------------------------------------------
    // Spoon side
    // ----------------------------------------------------------------
    Launcher launcher = new Launcher();
    launcher.addInputResource(SOURCE_PATH);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setCommentEnabled(false);
    launcher.buildModel();

    CtMethod<?> ctMethod =
        launcher.getFactory().Type().get(CLASS_NAME).getMethodsByName(METHOD_NAME).get(0);

    ControlFlowBuilder builder = new ControlFlowBuilder();
    builder.build(ctMethod);
    ControlFlowGraph spoonGraph = builder.getResult();
    spoonGraph.simplifyConvergenceNodes();

    System.out.println("\n=== SPOON CFG NODES ===");
    for (ControlFlowNode n : spoonGraph.vertexSet()) {
      if (n.getStatement() == null) {
        System.out.printf("  [kind=%-12s] (no statement — %s)%n", n.getKind(), n.getKind());
        continue;
      }
      int line =
          n.getStatement().getPosition().isValidPosition()
              ? n.getStatement().getPosition().getLine()
              : -1;
      int col =
          n.getStatement().getPosition().isValidPosition()
              ? n.getStatement().getPosition().getColumn()
              : -1;
      List<String> vars =
          n.getStatement().getElements(new TypeFilter<>(CtVariableAccess.class)).stream()
              .map(
                  va -> {
                    try {
                      return va.getVariable().getSimpleName()
                          + " ("
                          + (va.getType() != null ? va.getType().getSimpleName() : "?")
                          + ")";
                    } catch (Exception e) {
                      return va.getVariable().getSimpleName() + " (?)";
                    }
                  })
              .distinct()
              .toList();
      System.out.printf(
          "  [kind=%-12s, line %3d, col %2d] %s%n    vars: %s%n",
          n.getKind(), line, col, n.getStatement(), vars);
    }

    System.out.println("\n=== SPOON CFG EDGES ===");
    for (ControlFlowEdge e : spoonGraph.edgeSet()) {
      System.out.printf(
          "  %s -> %s%s%n",
          e.getSourceNode().getId(), e.getTargetNode().getId(), e.isBackEdge() ? " [back]" : "");
    }

    // ----------------------------------------------------------------
    // Side-by-side comparison matched by source line
    // ----------------------------------------------------------------
    Map<Integer, List<Stmt>> sootupByLine =
        sootNodes.stream().collect(Collectors.groupingBy(StmtAnalyzer::stmtLine));

    Map<Integer, List<ControlFlowNode>> spoonByLine =
        spoonGraph.vertexSet().stream()
            .filter(
                n ->
                    n.getStatement() != null
                        && n.getStatement().getPosition().isValidPosition()
                        && (n.getKind() == BranchKind.STATEMENT
                            || n.getKind() == BranchKind.BRANCH))
            .collect(Collectors.groupingBy(n -> n.getStatement().getPosition().getLine()));

    Set<Integer> allLines = new TreeSet<>();
    allLines.addAll(sootupByLine.keySet());
    allLines.addAll(spoonByLine.keySet());

    System.out.println("\n=== SIDE-BY-SIDE COMPARISON (matched by source line) ===");
    for (int line : allLines) {
      if (line <= 0) continue;
      System.out.printf("%n--- Line %d ---%n", line);

      List<Stmt> su = sootupByLine.getOrDefault(line, List.of());
      List<ControlFlowNode> sp = spoonByLine.getOrDefault(line, List.of());

      if (su.isEmpty()) {
        System.out.println("  SOOTUP : (no match)");
      } else {
        su.forEach(s -> System.out.printf("  SOOTUP : %s%n", s));
      }

      if (sp.isEmpty()) {
        System.out.println("  SPOON  : (no match)");
      } else {
        sp.forEach(
            n -> {
              int col = n.getStatement().getPosition().getColumn();
              List<String> vars =
                  n.getStatement().getElements(new TypeFilter<>(CtVariableAccess.class)).stream()
                      .map(
                          va -> {
                            try {
                              return va.getVariable().getSimpleName()
                                  + " ("
                                  + (va.getType() != null ? va.getType().getSimpleName() : "?")
                                  + ")";
                            } catch (Exception e) {
                              return va.getVariable().getSimpleName() + " (?)";
                            }
                          })
                      .distinct()
                      .toList();
              System.out.printf(
                  "  SPOON  : %s  [col %d]%n           vars: %s%n", n.getStatement(), col, vars);
            });
      }
    }

    long matched =
        allLines.stream()
            .filter(l -> l > 0 && sootupByLine.containsKey(l) && spoonByLine.containsKey(l))
            .count();
    System.out.printf(
        "%n=== SUMMARY: SootUp nodes=%d  Spoon nodes=%d  matched-by-line=%d ===%n",
        sootNodes.size(), spoonGraph.vertexSet().size(), matched);

    // ----------------------------------------------------------------
    // Generate SVGs
    // ----------------------------------------------------------------
    writeDotAndSvg(sootupToDot(sootNodes, stmtGraph), "sootup-cfg");
    writeDotAndSvg(spoonGraph.toGraphVisText(), "spoon-cfg");
  }

  @Test
  void checkInterfaceDispatch() throws Exception {
    Launcher launcher = new Launcher();
    launcher.addInputResource(SOURCE_PATH);
    launcher.getEnvironment().setNoClasspath(false);
    launcher.buildModel();

    CtMethod<?> ctMethod =
        launcher.getFactory().Type().get(CLASS_NAME).getMethodsByName(METHOD_NAME).get(0);

    ControlFlowBuilder builder = new ControlFlowBuilder();
    builder.build(ctMethod);
    ControlFlowGraph spoonGraph = builder.getResult();
    spoonGraph.simplifyConvergenceNodes();
    writeDotAndSvg(spoonGraph.toGraphVisText(), "spoon-cfg-dispatch");

    System.out.println("\n=== SPOON CFG — INVOCATION DISPATCH KINDS ===");
    for (ControlFlowNode n : spoonGraph.vertexSet()) {
      if (n.getStatement() == null) continue;
      List<CtInvocation<?>> invocations =
          n.getStatement().getElements(new TypeFilter<>(CtInvocation.class));
      for (CtInvocation<?> inv : invocations) {
        var exec = inv.getExecutable();
        var declaringType = exec.getDeclaringType();
        boolean isInterface = declaringType != null && declaringType.isInterface();
        boolean isStatic = exec.isStatic();
        String dispatchKind = isStatic ? "static" : (isInterface ? "interface" : "virtual");
        System.out.printf(
            "  call: %s.%s%n    declaring-type: %s  isInterface=%b  dispatch=%s%n",
            declaringType != null ? declaringType.getSimpleName() : "?",
            exec.getSimpleName(),
            declaringType != null ? declaringType.getQualifiedName() : "?",
            isInterface,
            dispatchKind);
      }
    }
  }

  private String sootupToDot(List<Stmt> nodes, StmtGraph<?> g) {
    StringBuilder sb =
        new StringBuilder(
            "digraph sootup_cfg {\n  rankdir=TB;\n  node [shape=box fontname=monospace];\n");
    for (int i = 0; i < nodes.size(); i++) {
      Stmt s = nodes.get(i);
      String label = s.toString().replace("\"", "\\\"").replace("\n", "\\n");
      int line = StmtAnalyzer.stmtLine(s);
      sb.append(String.format("  n%d [label=\"[L%d] %s\"];\n", i, line, label));
    }
    for (int i = 0; i < nodes.size(); i++) {
      for (Stmt dst : g.successors(nodes.get(i))) {
        int j = nodes.indexOf(dst);
        if (j >= 0) sb.append(String.format("  n%d -> n%d;\n", i, j));
      }
    }
    sb.append("}\n");
    return sb.toString();
  }

  private void writeDotAndSvg(String dot, String baseName) throws Exception {
    java.nio.file.Path targetDir = java.nio.file.Path.of("target");
    java.nio.file.Files.createDirectories(targetDir);
    java.nio.file.Path dotFile = targetDir.resolve(baseName + ".dot");
    java.nio.file.Path svgFile = targetDir.resolve(baseName + ".svg");
    java.nio.file.Files.writeString(dotFile, dot);
    Process p =
        new ProcessBuilder("dot", "-Tsvg", "-o", svgFile.toString(), dotFile.toString())
            .redirectErrorStream(true)
            .start();
    int exit = p.waitFor();
    String out = new String(p.getInputStream().readAllBytes());
    if (exit != 0) {
      System.err.println("[dot failed exit=" + exit + "]: " + out);
    } else {
      System.out.println("SVG written: " + svgFile.toAbsolutePath());
    }
  }
}
