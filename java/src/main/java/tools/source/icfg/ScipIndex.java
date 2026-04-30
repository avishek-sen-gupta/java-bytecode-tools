package tools.source.icfg;

import com.sourcegraph.Scip;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class ScipIndex {

  private final Map<String, SourceLocation> definitionIndex = new HashMap<>();

  public ScipIndex(Path indexPath) throws IOException {
    Scip.Index index = Scip.Index.parseFrom(Files.readAllBytes(indexPath));
    for (Scip.Document doc : index.getDocumentsList()) {
      String file = doc.getRelativePath();
      for (Scip.Occurrence occ : doc.getOccurrencesList()) {
        if ((occ.getSymbolRoles() & 1) != 0) { // SymbolRole.Definition = 1
          List<Integer> range = occ.getRangeList();
          int startLine = range.get(0) + 1; // 0-indexed → 1-indexed
          int endLine = range.size() == 4 ? range.get(2) + 1 : startLine;
          definitionIndex.put(occ.getSymbol(), new SourceLocation(file, startLine, endLine));
        }
      }
    }
  }

  public SourceLocation locationOf(String fqn, String methodName) {
    String matchKey = fqn.replace('.', '/') + "#" + methodName + "().";
    return definitionIndex.entrySet().stream()
        .filter(e -> e.getKey().contains(matchKey))
        .map(Map.Entry::getValue)
        .findFirst()
        .orElseThrow(
            () ->
                new IllegalArgumentException(
                    "No SCIP definition found for " + fqn + "#" + methodName));
  }

  public boolean hasDefinition(String fqn, String methodName) {
    String matchKey = fqn.replace('.', '/') + "#" + methodName + "().";
    return definitionIndex.keySet().stream().anyMatch(k -> k.contains(matchKey));
  }
}
