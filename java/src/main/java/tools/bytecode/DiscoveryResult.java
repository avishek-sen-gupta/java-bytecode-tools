package tools.bytecode;

import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Result of Pass 1 call graph discovery.
 *
 * @param normalMethods signatures of methods that should have full CFGs built
 * @param calleeMap for each discovered method, the list of callees with per-call-site
 *     classification
 */
public record DiscoveryResult(Set<String> normalMethods, Map<String, List<CalleeEntry>> calleeMap) {

  /** A single callee at a specific call site, with its classification. */
  public record CalleeEntry(String signature, Classification classification) {}

  public DiscoveryResult {
    normalMethods = Set.copyOf(normalMethods);
    calleeMap = Map.copyOf(calleeMap);
  }
}
