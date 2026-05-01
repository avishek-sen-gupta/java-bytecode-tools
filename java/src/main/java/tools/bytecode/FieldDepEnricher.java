package tools.bytecode;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import tools.bytecode.artifact.DdgEdge;
import tools.bytecode.artifact.DdgGraph;
import tools.bytecode.artifact.DdgNode;
import tools.bytecode.artifact.HeapEdge;

public class FieldDepEnricher {

  @FunctionalInterface
  public interface AliasCheck {
    boolean test(String methodSigA, String localA, String methodSigB, String localB);
  }

  // Read:  "$count = receiver.<com.example.A: int f>"
  private static final Pattern FIELD_READ =
      Pattern.compile("^([\\w$][\\w$]*) = ([\\w$][\\w$]*)\\.<(.+)>$");

  // Write: "receiver.<com.example.A: int f> = val"
  private static final Pattern FIELD_WRITE =
      Pattern.compile("^([\\w$][\\w$]*)\\.(<.+>) = ([\\w$][\\w$]*)$");

  private final AliasCheck aliasCheck;

  public FieldDepEnricher(AliasCheck aliasCheck) {
    this.aliasCheck = aliasCheck;
  }

  public DdgGraph enrich(DdgGraph ddg, Set<String> inScopeMethodSigs) {
    List<DdgEdge> newEdges = new ArrayList<>(ddg.edges());

    for (DdgNode readNode : ddg.nodes()) {
      if (!inScopeMethodSigs.contains(readNode.method())) continue;
      Matcher readMatcher = FIELD_READ.matcher(readNode.stmt());
      if (!readMatcher.matches()) continue;

      String readReceiver = readMatcher.group(2);
      String fieldSig = "<" + readMatcher.group(3) + ">";

      for (DdgNode writeNode : ddg.nodes()) {
        if (!inScopeMethodSigs.contains(writeNode.method())) continue;
        Matcher writeMatcher = FIELD_WRITE.matcher(writeNode.stmt());
        if (!writeMatcher.matches()) continue;

        String writeFieldSig = writeMatcher.group(2);
        if (!fieldSig.equals(writeFieldSig)) continue;

        String writeReceiver = writeMatcher.group(1);

        if (!aliasCheck.test(writeNode.method(), writeReceiver, readNode.method(), readReceiver))
          continue;

        newEdges.add(new DdgEdge(writeNode.id(), readNode.id(), new HeapEdge(fieldSig)));
      }
    }

    return new DdgGraph(ddg.nodes(), newEdges);
  }
}
