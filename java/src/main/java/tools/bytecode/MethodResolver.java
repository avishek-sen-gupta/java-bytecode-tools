package tools.bytecode;

import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import sootup.core.model.SootMethod;
import sootup.core.signatures.MethodSignature;
import sootup.core.types.ClassType;
import sootup.java.core.JavaSootClass;
import sootup.java.core.views.JavaView;

class MethodResolver {

  private final JavaView view;

  MethodResolver(JavaView view) {
    this.view = view;
  }

  /** Resolve a method in a class by name. Throws if not found or ambiguous. */
  SootMethod resolveByName(String className, String methodName) {
    ClassType type = view.getIdentifierFactory().getClassType(className);
    Optional<JavaSootClass> clsOpt = view.getClass(type);
    if (clsOpt.isEmpty()) {
      throw new RuntimeException("Class not found: " + className);
    }
    List<SootMethod> matches =
        clsOpt.get().getMethods().stream()
            .filter(m -> m.getName().equals(methodName) && m.hasBody())
            .collect(Collectors.toList());
    if (matches.isEmpty()) {
      throw new RuntimeException("No method named '" + methodName + "' in " + className);
    }
    if (matches.size() > 1) {
      StringBuilder sb = new StringBuilder();
      sb.append("Ambiguous: ")
          .append(matches.size())
          .append(" overloads for '")
          .append(methodName)
          .append("' in ")
          .append(className)
          .append(":\n");
      for (SootMethod m : matches) {
        int lineStart =
            m.getBody().getStmtGraph().getNodes().stream()
                .mapToInt(StmtAnalyzer::stmtLine)
                .filter(l -> l > 0)
                .min()
                .orElse(-1);
        sb.append("  ").append(m.getSignature()).append(" (line ").append(lineStart).append(")\n");
      }
      sb.append("Use --from-line to disambiguate.");
      throw new RuntimeException(sb.toString());
    }
    return matches.get(0);
  }

  /** Resolve a method in a class by line number. Throws if not found. */
  SootMethod resolveByLine(String className, int line) {
    ClassType type = view.getIdentifierFactory().getClassType(className);
    Optional<JavaSootClass> clsOpt = view.getClass(type);
    if (clsOpt.isEmpty()) {
      throw new RuntimeException("Class not found: " + className);
    }
    List<SootMethod> methods = findMethodsContainingLine(clsOpt.get(), line);
    if (methods.isEmpty()) {
      throw new RuntimeException("No method containing line " + line + " in " + className);
    }
    return methods.get(0);
  }

  /** Resolve a method by its full Soot signature string. Throws if not found. */
  SootMethod resolveBySignature(String methodSignature) {
    String className =
        extractDeclaringClass(methodSignature).orElseThrow(() -> methodNotFound(methodSignature));
    ClassType type = view.getIdentifierFactory().getClassType(className);
    Optional<JavaSootClass> clsOpt = view.getClass(type);
    if (clsOpt.isEmpty()) {
      throw methodNotFound(methodSignature);
    }
    return clsOpt.get().getMethods().stream()
        .filter(method -> method.getSignature().toString().equals(methodSignature))
        .findFirst()
        .orElseThrow(() -> methodNotFound(methodSignature));
  }

  /**
   * Resolve a callee method by signature. Returns Optional.empty() if the class is not in the view
   * or if the method cannot be found, never returns null.
   */
  Optional<SootMethod> resolveCallee(MethodSignature sig) {
    ClassType declType = sig.getDeclClassType();
    Optional<JavaSootClass> clsOpt = view.getClass(declType);
    if (clsOpt.isEmpty()) {
      return Optional.empty();
    }
    JavaSootClass cls = clsOpt.get();

    try {
      Optional<? extends SootMethod> mOpt = cls.getMethod(sig.getSubSignature());
      if (mOpt.isPresent() && mOpt.get().hasBody()) {
        return mOpt.map(m -> (SootMethod) m);
      }
    } catch (Exception ignored) {
    }

    int paramCount = sig.getParameterTypes().size();
    return cls.getMethods().stream()
        .filter(
            m ->
                m.getName().equals(sig.getName())
                    && m.getParameterCount() == paramCount
                    && m.hasBody())
        .findFirst()
        .map(m -> (SootMethod) m);
  }

  /** Find all methods in a class that contain the given line number. */
  List<SootMethod> findMethodsContainingLine(JavaSootClass clazz, int line) {
    return clazz.getMethods().stream()
        .filter(method -> method.hasBody() && containsLine(method, line))
        .collect(Collectors.toList());
  }

  private boolean containsLine(SootMethod method, int line) {
    return method.getBody().getStmtGraph().getNodes().stream()
        .anyMatch(stmt -> StmtAnalyzer.stmtLine(stmt) == line);
  }

  private static Optional<String> extractDeclaringClass(String methodSignature) {
    if (!methodSignature.startsWith("<") || !methodSignature.endsWith(">")) {
      return Optional.empty();
    }
    int colonIndex = methodSignature.indexOf(':');
    if (colonIndex <= 1) {
      return Optional.empty();
    }
    return Optional.of(methodSignature.substring(1, colonIndex));
  }

  private static RuntimeException methodNotFound(String methodSignature) {
    return new RuntimeException("Method not found: " + methodSignature);
  }
}
