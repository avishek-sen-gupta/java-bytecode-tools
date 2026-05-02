package tools.bytecode;

import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import tools.bytecode.artifact.DdgEdge;
import tools.bytecode.artifact.DdgNode;
import tools.bytecode.artifact.LocalEdge;
import tools.bytecode.artifact.ReturnEdge;
import tools.bytecode.artifact.StmtKind;

public class InterProcEdgeBuilder {

  private static final Pattern NUMERIC_LITERAL = Pattern.compile("^-?\\d+(\\.\\d+)?[LlFfDd]?$");

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
  public static List<DdgEdge> buildReturnEdges(
      List<DdgNode> nodes, List<Map<String, Object>> calls) {
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
                                  && callee.equals(n.call().get("targetMethodSignature")))
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
   * Extract the argument name at position {@code paramIndex} from a Jimple call-site statement.
   * Returns empty string if index is out of bounds or the arg list is empty.
   */
  public static String extractArgLocal(String stmt, int paramIndex) {
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
  public static String findReachingDefId(
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
  public static boolean isConstantArg(String arg) {
    if (arg.isEmpty()) return true;
    if ("null".equals(arg) || "true".equals(arg) || "false".equals(arg)) return true;
    if (arg.startsWith("\"")) return true;
    return NUMERIC_LITERAL.matcher(arg).matches();
  }
}
