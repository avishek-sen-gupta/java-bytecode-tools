package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.file.Paths;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import sootup.core.model.SootMethod;

class BytecodeTracerResolveByNameTest {

  private static BytecodeTracer tracer;

  private static final String CLASSPATH =
      Paths.get("../test-fixtures/classes").toAbsolutePath().toString();

  @BeforeAll
  static void setUp() {
    tracer = new BytecodeTracer(CLASSPATH);
    tracer.setProjectPrefix("com.example.app");
  }

  @Nested
  class UniqueMatch {

    @Test
    void returnsMethodWhenNameIsUnique() {
      SootMethod method =
          tracer.resolveMethodByName("com.example.app.OrderService", "processOrder");
      assertEquals("processOrder", method.getName());
    }

    @Test
    void returnsMethodForUniqueNameInOverloadedClass() {
      SootMethod method = tracer.resolveMethodByName("com.example.app.OverloadedService", "unique");
      assertEquals("unique", method.getName());
    }
  }

  @Nested
  class NoMatch {

    @Test
    void throwsWithMessageWhenMethodNotFound() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> tracer.resolveMethodByName("com.example.app.OrderService", "nonexistent"));
      assertTrue(
          ex.getMessage().contains("No method named 'nonexistent'"),
          "Expected 'No method named' message, got: " + ex.getMessage());
      assertTrue(
          ex.getMessage().contains("com.example.app.OrderService"),
          "Expected class name in message");
    }
  }

  @Nested
  class AmbiguousMatch {

    @Test
    void throwsWhenMultipleOverloadsExist() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> tracer.resolveMethodByName("com.example.app.OverloadedService", "process"));
      assertTrue(
          ex.getMessage().contains("Ambiguous"),
          "Expected 'Ambiguous' in message, got: " + ex.getMessage());
    }

    @Test
    void errorListsEachOverloadSignature() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> tracer.resolveMethodByName("com.example.app.OverloadedService", "process"));
      // Both overloads should be listed
      assertTrue(
          ex.getMessage().contains("int") || ex.getMessage().contains("String"),
          "Expected overload parameter types in message, got: " + ex.getMessage());
    }

    @Test
    void errorIncludesLineNumbers() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> tracer.resolveMethodByName("com.example.app.OverloadedService", "process"));
      assertTrue(
          ex.getMessage().contains("line"),
          "Expected 'line' in error message, got: " + ex.getMessage());
    }

    @Test
    void errorSuggestsFromLineFlag() {
      RuntimeException ex =
          assertThrows(
              RuntimeException.class,
              () -> tracer.resolveMethodByName("com.example.app.OverloadedService", "process"));
      assertTrue(
          ex.getMessage().contains("--from-line"),
          "Expected '--from-line' suggestion in message, got: " + ex.getMessage());
    }
  }
}
