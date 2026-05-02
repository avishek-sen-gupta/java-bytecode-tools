package tools.bytecode;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import sootup.core.graph.StmtGraph;
import sootup.core.jimple.common.stmt.Stmt;
import sootup.core.model.Body;
import sootup.core.model.SootMethod;
import sootup.core.types.ClassType;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

class LineMapReporter {

  private final JavaView view;
  private final StmtAnalyzer stmtAnalyzer;

  LineMapReporter(JavaView view, StmtAnalyzer stmtAnalyzer) {
    this.view = view;
    this.stmtAnalyzer = stmtAnalyzer;
  }

  Map<String, Object> dumpLineMap(String className) {
    ClassType classType = view.getIdentifierFactory().getClassType(className);
    JavaSootClass clazz =
        view.getClass(classType)
            .orElseThrow(() -> new RuntimeException("Class not found: " + className));
    List<Map<String, Object>> methods =
        clazz.getMethods().stream()
            .filter(SootMethod::hasBody)
            .map(this::buildMethodLineMap)
            .collect(Collectors.toList());
    Map<String, Object> result = new LinkedHashMap<>();
    result.put("class", className);
    result.put("methodCount", methods.size());
    result.put("methods", methods);
    return result;
  }

  private Map<String, Object> buildMethodLineMap(SootMethod method) {
    Body body = method.getBody();
    StmtGraph<?> graph = body.getStmtGraph();
    List<Stmt> nodes = new ArrayList<>(graph.getNodes());
    Map<Integer, Integer> lineCounts =
        nodes.stream()
            .collect(Collectors.toMap(stmtAnalyzer::stmtLine, s -> 1, Integer::sum, TreeMap::new));
    int minLine = stmtAnalyzer.minLine(nodes);
    int maxLine = stmtAnalyzer.maxLine(nodes);
    Map<String, Object> m = new LinkedHashMap<>();
    m.put("method", method.getName());
    m.put("signature", method.getSignature().toString());
    m.put("lineStart", minLine);
    m.put("lineEnd", maxLine);
    m.put("stmtCount", nodes.size());
    m.put("sourceLines", lineCounts.size());
    m.put("lineMap", lineCounts);
    return m;
  }
}
