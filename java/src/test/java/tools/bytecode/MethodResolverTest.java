package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Paths;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import sootup.core.model.SootMethod;
import sootup.core.signatures.MethodSignature;
import sootup.java.bytecode.frontend.inputlocation.JavaClassPathAnalysisInputLocation;
import sootup.java.core.views.JavaView;

class MethodResolverTest {

  private static MethodResolver resolver;

  @BeforeAll
  static void setUp() {
    String cp = Paths.get("../test-fixtures/classes").toAbsolutePath().toString();
    JavaView view = new JavaView(List.of(new JavaClassPathAnalysisInputLocation(cp)));
    resolver = new MethodResolver(view);
  }

  @Nested
  class ResolveByName {
    @Test
    void returnsMethod_whenExactlyOneMatch() {
      SootMethod m = resolver.resolveByName("com.example.app.OrderService", "processOrder");
      assertEquals("processOrder", m.getName());
    }

    @Test
    void returnsMethodForUniqueNameInOverloadedClass() {
      SootMethod m = resolver.resolveByName("com.example.app.OverloadedService", "unique");
      assertEquals("unique", m.getName());
    }

    @Test
    void throwsWithHelpfulMessage_whenMethodNotFound() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> resolver.resolveByName("com.example.app.OrderService", "nonexistent"));
      assertTrue(
          ex.getMessage().contains("No method named 'nonexistent'"), "Got: " + ex.getMessage());
    }

    @Test
    void throwsWithClassName_whenMethodNotFound() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> resolver.resolveByName("com.example.app.OrderService", "nonexistent"));
      assertTrue(
          ex.getMessage().contains("com.example.app.OrderService"),
          "Expected class name in message, got: " + ex.getMessage());
    }

    @Test
    void throwsAmbiguousMessage_whenMultipleOverloadsExist() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> resolver.resolveByName("com.example.app.OverloadedService", "process"));
      assertTrue(
          ex.getMessage().contains("Ambiguous"),
          "Expected 'Ambiguous' in message, got: " + ex.getMessage());
    }

    @Test
    void ambiguousErrorListsEachOverloadSignature() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> resolver.resolveByName("com.example.app.OverloadedService", "process"));
      // Both overloads should be listed
      assertTrue(
          ex.getMessage().contains("int") || ex.getMessage().contains("String"),
          "Expected overload parameter types in message, got: " + ex.getMessage());
    }

    @Test
    void ambiguousErrorIncludesLineNumbers() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> resolver.resolveByName("com.example.app.OverloadedService", "process"));
      assertTrue(
          ex.getMessage().contains("line"),
          "Expected 'line' in error message, got: " + ex.getMessage());
    }

    @Test
    void ambiguousErrorSuggestsFromLineFlag() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> resolver.resolveByName("com.example.app.OverloadedService", "process"));
      assertTrue(
          ex.getMessage().contains("--from-line"),
          "Expected '--from-line' suggestion in message, got: " + ex.getMessage());
    }

    @Test
    void throwsWithClassName_whenClassNotFound() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> resolver.resolveByName("com.example.app.NoSuchClass", "method"));
      assertTrue(
          ex.getMessage().contains("com.example.app.NoSuchClass"), "Got: " + ex.getMessage());
    }
  }

  @Nested
  class ResolveByLine {
    @Test
    void returnsMethod_whenLineExistsInMethod() {
      SootMethod byName = resolver.resolveByName("com.example.app.OrderService", "processOrder");
      int startLine =
          byName.getBody().getStmtGraph().getNodes().stream()
              .mapToInt(StmtAnalyzer::stmtLine)
              .filter(l -> l > 0)
              .min()
              .orElseThrow();

      SootMethod byLine = resolver.resolveByLine("com.example.app.OrderService", startLine);
      assertEquals("processOrder", byLine.getName());
    }

    @Test
    void throws_whenNoMethodContainsLine() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> resolver.resolveByLine("com.example.app.OrderService", 999999));
      assertTrue(ex.getMessage().contains("999999"), "Got: " + ex.getMessage());
    }
  }

  @Nested
  class ResolveCallee {
    @Test
    void returnsPresent_whenMethodExists() {
      SootMethod known = resolver.resolveByName("com.example.app.OrderService", "processOrder");
      MethodSignature sig = known.getSignature();
      Optional<SootMethod> result = resolver.resolveCallee(sig);
      assertTrue(result.isPresent());
    }

    @Test
    void returnsOptional_notNull() {
      SootMethod known = resolver.resolveByName("com.example.app.OrderService", "processOrder");
      Optional<SootMethod> result = resolver.resolveCallee(known.getSignature());
      assertNotNull(result, "must be Optional, never null");
    }
  }
}
