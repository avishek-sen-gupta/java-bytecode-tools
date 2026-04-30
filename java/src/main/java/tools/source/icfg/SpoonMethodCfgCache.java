package tools.source.icfg;

import fr.inria.controlflow.ControlFlowBuilder;
import fr.inria.controlflow.ControlFlowGraph;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import spoon.Launcher;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;

public class SpoonMethodCfgCache {

  private final Launcher launcher;
  private final Map<String, ControlFlowGraph> cache = new HashMap<>();

  public SpoonMethodCfgCache(String sourceRoot) {
    launcher = new Launcher();
    launcher.addInputResource(sourceRoot);
    launcher.getEnvironment().setNoClasspath(true);
    launcher.getEnvironment().setCommentEnabled(false);
    launcher.buildModel();
  }

  public ControlFlowGraph cfgFor(String fqn, int startLine) {
    String key = fqn + ":" + startLine;
    return cache.computeIfAbsent(key, k -> buildCfg(fqn, startLine));
  }

  private ControlFlowGraph buildCfg(String fqn, int startLine) {
    CtType<?> ctType = launcher.getFactory().Type().get(fqn);
    if (ctType == null) {
      throw new IllegalArgumentException("Type not found in source root: " + fqn);
    }
    CtMethod<?> method =
        ctType.getMethods().stream()
            .filter(
                m -> m.getPosition().isValidPosition() && m.getPosition().getLine() <= startLine)
            .max(Comparator.comparingInt(m -> m.getPosition().getLine()))
            .orElseThrow(
                () ->
                    new IllegalArgumentException(
                        "No method found in " + fqn + " at or before line " + startLine));
    ControlFlowBuilder builder = new ControlFlowBuilder();
    builder.build(method);
    ControlFlowGraph cfg = builder.getResult();
    cfg.simplifyConvergenceNodes();
    return cfg;
  }
}
