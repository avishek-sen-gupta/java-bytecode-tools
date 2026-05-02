package tools.bytecode;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import tools.bytecode.artifact.DdgEdge;
import tools.bytecode.artifact.DdgNode;
import tools.bytecode.artifact.LocalEdge;
import tools.bytecode.artifact.ParamEdge;
import tools.bytecode.artifact.ReturnEdge;
import tools.bytecode.artifact.StmtKind;

public class InterProcEdgeBuilder {

  private static final Pattern NUMERIC_LITERAL = Pattern.compile("^-?\\d+(\\.\\d+)?[LlFfDd]?$");
  private static final Pattern PARAM_IDENTITY =
      Pattern.compile("^\\w[\\w$#]* := @parameter(\\d+):");

  private record ParamTarget(DdgNode node, int index) {}

  /**
   * Build all inter-procedural edges (PARAM + RETURN) from DDG nodes, LOCAL edges, and call list.
   */
  public List<DdgEdge> build(
      List<DdgNode> nodes, List<DdgEdge> localEdges, List<Map<String, Object>> calls) {
    List<DdgEdge> result = new ArrayList<>();
    result.addAll(buildParamEdges(nodes, localEdges, calls));
    result.addAll(buildReturnEdges(nodes, calls));
    return result;
  }

  /**
   * Builds RETURN edges from callee RETURN nodes to caller ASSIGN_INVOKE call sites.
   *
   * <p>For each call {from: callerSig, to: calleeSig}: - Find RETURN nodes in callee - Find
   * ASSIGN_INVOKE nodes in caller targeting calleeSig - For each (returnNode, assignInvokeNode)
   * pair, emit a RETURN edge
   *
   * @param nodes List of DdgNode objects across all methods
   * @param calls List of call maps with "from" (caller) and "to" (callee) signatures
   * @return List of DdgEdge objects representing RETURN edges
   */
  public List<DdgEdge> buildReturnEdges(List<DdgNode> nodes, List<Map<String, Object>> calls) {
    return calls.stream()
        .flatMap(
            call -> {
              String caller = (String) call.get("from");
              String callee = (String) call.get("to");

              // Find RETURN nodes in callee
              List<DdgNode> returnNodes =
                  nodes.stream()
                      .filter(n -> n.method().equals(callee) && n.kind() == StmtKind.RETURN)
                      .toList();

              // Find ASSIGN_INVOKE nodes in caller targeting callee
              List<DdgNode> assignInvokeNodes =
                  nodes.stream()
                      .filter(
                          n ->
                              n.method().equals(caller)
                                  && n.kind() == StmtKind.ASSIGN_INVOKE
                                  && matchesSubSignature(
                                      callee, (String) n.call().get("targetMethodSignature")))
                      .toList();

              // Create RETURN edges from each return node to each assign-invoke node
              return returnNodes.stream()
                  .flatMap(
                      returnNode ->
                          assignInvokeNodes.stream()
                              .map(
                                  assignInvokeNode ->
                                      new DdgEdge(
                                          returnNode.id(),
                                          assignInvokeNode.id(),
                                          new ReturnEdge())));
            })
        .toList();
  }

  /**
   * Extract the sub-signature (method name + parameter types) from a full Soot method signature.
   * E.g., from {@code <com.example.Foo: int bar(String,int)>} returns {@code bar(String,int)}.
   */
  public String extractSubSignature(String methodSignature) {
    int parenOpen = methodSignature.indexOf('(');
    if (parenOpen < 0) return methodSignature;
    int nameStart = methodSignature.lastIndexOf(' ', parenOpen) + 1;
    int parenClose = methodSignature.lastIndexOf(')');
    if (parenClose < 0) return methodSignature;
    return methodSignature.substring(nameStart, parenClose + 1);
  }

  private boolean matchesSubSignature(String calltreeSig, String callSiteSig) {
    if (callSiteSig == null) return false;
    return extractSubSignature(calltreeSig).equals(extractSubSignature(callSiteSig));
  }

  /**
   * Extract the argument name at position {@code paramIndex} from a Jimple call-site statement.
   * Returns empty string if index is out of bounds or the arg list is empty.
   */
  public String extractArgLocal(String stmt, int paramIndex) {
    int open = stmt.lastIndexOf('(');
    int close = stmt.lastIndexOf(')');
    if (open < 0 || close < 0 || close <= open) return "";
    String args = stmt.substring(open + 1, close).trim();
    if (args.isEmpty()) return "";
    String[] parts = args.split(",");
    if (paramIndex >= parts.length) return "";
    return parts[paramIndex].trim();
  }

  /**
   * Find the reaching-def node ID for a given local at a call site. Scans LOCAL edges pointing to
   * {@code callSiteNodeId}, checks if the source node defines {@code argLocal} (via {@code x = ...}
   * or {@code x := ...}). Returns empty string if no reaching-def found.
   */
  public String findReachingDefId(
      String callSiteNodeId, String argLocal, List<DdgEdge> edges, Map<String, DdgNode> nodeIndex) {
    return edges.stream()
        .filter(e -> callSiteNodeId.equals(e.to()))
        .filter(e -> e.edgeInfo() instanceof LocalEdge)
        .filter(
            e -> {
              DdgNode fromNode = nodeIndex.get(e.from());
              if (fromNode == null) return false;
              String stmt = fromNode.stmt();
              return stmt.startsWith(argLocal + " = ") || stmt.startsWith(argLocal + " := ");
            })
        .map(DdgEdge::from)
        .findFirst()
        .orElse("");
  }

  /**
   * Returns true if the argument string is a Jimple constant (no reaching-def to track). Constants:
   * null, true, false, numeric literals, string literals, empty string.
   */
  public boolean isConstantArg(String arg) {
    if (arg.isEmpty()) return true;
    if ("null".equals(arg) || "true".equals(arg) || "false".equals(arg)) return true;
    if (arg.startsWith("\"")) return true;
    return NUMERIC_LITERAL.matcher(arg).matches();
  }

  /**
   * PARAM edges: connect reaching-def of each argument at the call site to the corresponding
   *
   * @parameterN IDENTITY node in the callee.
   *     <p>Skips: @this identity, constant arguments, arguments with no reaching-def.
   */
  public List<DdgEdge> buildParamEdges(
      List<DdgNode> nodes, List<DdgEdge> localEdges, List<Map<String, Object>> calls) {

    Map<String, DdgNode> nodeIndex = new HashMap<>();
    for (DdgNode n : nodes) nodeIndex.put(n.id(), n);

    List<DdgEdge> edges = new ArrayList<>();

    for (Map<String, Object> call : calls) {
      String callerSig = (String) call.get("from");
      String calleeSig = (String) call.get("to");

      // Find @parameterN IDENTITY nodes in callee (skip @this)
      List<ParamTarget> paramTargets =
          nodes.stream()
              .filter(n -> n.method().equals(calleeSig) && n.kind() == StmtKind.IDENTITY)
              .flatMap(
                  n -> {
                    Matcher m = PARAM_IDENTITY.matcher(n.stmt());
                    if (!m.find()) return Stream.empty();
                    int idx = Integer.parseInt(m.group(1));
                    return Stream.of(new ParamTarget(n, idx));
                  })
              .toList();

      // Find call-site nodes in caller targeting this callee
      List<DdgNode> callSiteNodes =
          nodes.stream()
              .filter(
                  n ->
                      n.method().equals(callerSig)
                          && (n.kind() == StmtKind.ASSIGN_INVOKE || n.kind() == StmtKind.INVOKE)
                          && matchesSubSignature(
                              calleeSig, (String) n.call().get("targetMethodSignature")))
              .toList();

      for (DdgNode callSiteNode : callSiteNodes) {
        for (ParamTarget pt : paramTargets) {
          String argLocal = extractArgLocal(callSiteNode.stmt(), pt.index());
          if (argLocal.isEmpty() || isConstantArg(argLocal)) continue;

          String reachingDefId =
              findReachingDefId(callSiteNode.id(), argLocal, localEdges, nodeIndex);
          if (reachingDefId.isEmpty()) continue;

          edges.add(new DdgEdge(reachingDefId, pt.node().id(), new ParamEdge()));
        }
      }
    }
    return edges;
  }
}
