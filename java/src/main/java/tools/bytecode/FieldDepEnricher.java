package tools.bytecode;

import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Stream;
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
    List<DdgEdge> heapEdges =
        ddg.nodes().stream()
            .filter(readNode -> inScopeMethodSigs.contains(readNode.method()))
            .flatMap(readNode -> matchFieldRead(readNode, ddg, inScopeMethodSigs))
            .toList();

    List<DdgEdge> allEdges = Stream.concat(ddg.edges().stream(), heapEdges.stream()).toList();
    return new DdgGraph(ddg.nodes(), allEdges);
  }

  private Stream<DdgEdge> matchFieldRead(
      DdgNode readNode, DdgGraph ddg, Set<String> inScopeMethodSigs) {
    Matcher readMatcher = FIELD_READ.matcher(readNode.stmt());
    if (!readMatcher.matches()) return Stream.empty();

    String readReceiver = readMatcher.group(2);
    String fieldSig = "<" + readMatcher.group(3) + ">";

    return ddg.nodes().stream()
        .filter(writeNode -> inScopeMethodSigs.contains(writeNode.method()))
        .flatMap(
            writeNode -> {
              Matcher writeMatcher = FIELD_WRITE.matcher(writeNode.stmt());
              if (!writeMatcher.matches()) return Stream.empty();
              if (!fieldSig.equals(writeMatcher.group(2))) return Stream.empty();
              if (!aliasCheck.test(
                  writeNode.method(), writeMatcher.group(1), readNode.method(), readReceiver))
                return Stream.empty();
              return Stream.of(new DdgEdge(writeNode.id(), readNode.id(), new HeapEdge(fieldSig)));
            });
  }
}
