package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

class BuildRefChildTest {

  private static final String SIG = "<com.example.Foo: void bar(int)>";
  private final ForwardTracer tracer = new ForwardTracer();

  @Nested
  class NormalRefTest {

    @Test
    void normalClassificationProducesRefNode() {
      Map<String, Object> node = tracer.buildChildNode(SIG, Classification.NORMAL, 42);

      assertEquals("com.example.Foo", node.get(ForwardTracer.F_CLASS));
      assertEquals("bar", node.get(ForwardTracer.F_METHOD));
      assertEquals(SIG, node.get(ForwardTracer.F_METHOD_SIGNATURE));
      assertEquals(true, node.get(ForwardTracer.F_REF));
      assertNull(node.get(ForwardTracer.F_CYCLE));
      assertNull(node.get(ForwardTracer.F_FILTERED));
      assertEquals(42, node.get(ForwardTracer.F_CALL_SITE_LINE));
    }
  }

  @Nested
  class CycleTest {

    @Test
    void cycleClassificationProducesCycleNode() {
      Map<String, Object> node = tracer.buildChildNode(SIG, Classification.CYCLE, 10);

      assertEquals(true, node.get(ForwardTracer.F_CYCLE));
      assertNull(node.get(ForwardTracer.F_REF));
      assertNull(node.get(ForwardTracer.F_FILTERED));
    }
  }

  @Nested
  class FilteredTest {

    @Test
    void filteredClassificationProducesFilteredNode() {
      Map<String, Object> node = tracer.buildChildNode(SIG, Classification.FILTERED, 5);

      assertEquals(true, node.get(ForwardTracer.F_FILTERED));
      assertNull(node.get(ForwardTracer.F_REF));
      assertNull(node.get(ForwardTracer.F_CYCLE));
    }
  }

  @Nested
  class CallSiteLineTest {

    @Test
    void positiveCallSiteLineIncluded() {
      Map<String, Object> node = tracer.buildChildNode(SIG, Classification.NORMAL, 42);

      assertEquals(42, node.get(ForwardTracer.F_CALL_SITE_LINE));
    }

    @Test
    void negativeCallSiteLineOmitted() {
      Map<String, Object> node = tracer.buildChildNode(SIG, Classification.NORMAL, -1);

      assertNull(node.get(ForwardTracer.F_CALL_SITE_LINE));
    }

    @Test
    void zeroCallSiteLineOmitted() {
      Map<String, Object> node = tracer.buildChildNode(SIG, Classification.NORMAL, 0);

      assertNull(node.get(ForwardTracer.F_CALL_SITE_LINE));
    }
  }

  @Nested
  class SignatureParsingTest {

    @Test
    void extractsClassAndMethodFromSignature() {
      Map<String, Object> node =
          tracer.buildChildNode(
              "<com.example.app.OrderService: void processOrder(int)>", Classification.NORMAL, 7);

      assertEquals("com.example.app.OrderService", node.get(ForwardTracer.F_CLASS));
      assertEquals("processOrder", node.get(ForwardTracer.F_METHOD));
    }
  }
}
