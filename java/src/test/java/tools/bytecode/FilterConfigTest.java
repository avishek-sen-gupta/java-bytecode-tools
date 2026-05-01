package tools.bytecode;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import org.junit.jupiter.api.Test;

class FilterConfigTest {

  @Test
  void shouldRecurse_returnsTrueWhenNoFilters() {
    FilterConfig cfg = new FilterConfig(List.of(), List.of());
    assertTrue(cfg.shouldRecurse("com.example.Foo"));
  }

  @Test
  void shouldRecurse_returnsTrueWhenClassMatchesAllowPrefix() {
    FilterConfig cfg = new FilterConfig(List.of("com.example"), List.of());
    assertTrue(cfg.shouldRecurse("com.example.Foo"));
  }

  @Test
  void shouldRecurse_returnsFalseWhenClassDoesNotMatchAllowPrefix() {
    FilterConfig cfg = new FilterConfig(List.of("com.example"), List.of());
    assertFalse(cfg.shouldRecurse("org.other.Bar"));
  }

  @Test
  void shouldRecurse_returnsFalseWhenClassMatchesStopPrefix() {
    FilterConfig cfg = new FilterConfig(List.of(), List.of("com.ext"));
    assertFalse(cfg.shouldRecurse("com.ext.External"));
  }

  @Test
  void shouldRecurse_returnsTrueWhenClassPassesBothAllowAndStop() {
    FilterConfig cfg = new FilterConfig(List.of("com.example"), List.of("com.ext"));
    assertTrue(cfg.shouldRecurse("com.example.Internal"));
  }

  @Test
  void shouldRecurse_returnsFalseWhenClassMatchesAllowButAlsoStop() {
    FilterConfig cfg = new FilterConfig(List.of("com.example"), List.of("com.example.bad"));
    assertFalse(cfg.shouldRecurse("com.example.bad.Excluded"));
  }

  @Test
  void load_returnsEmptyFilterConfigWhenPathIsNull() throws Exception {
    FilterConfig cfg = FilterConfig.load(null);
    assertTrue(cfg.shouldRecurse("com.anything.Foo"));
  }
}
