package tools.bytecode;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

public record FilterConfig(List<String> allow, List<String> stop) {

  boolean shouldRecurse(String className) {
    boolean passesAllow = allow.isEmpty() || allow.stream().anyMatch(className::startsWith);
    boolean passesStop = stop.isEmpty() || stop.stream().noneMatch(className::startsWith);
    return passesAllow && passesStop;
  }

  public static FilterConfig load(Path path) throws IOException {
    if (path == null) return new FilterConfig(List.of(), List.of());
    ObjectMapper m = new ObjectMapper();
    @SuppressWarnings("unchecked")
    Map<String, List<String>> raw = m.readValue(path.toFile(), Map.class);
    return new FilterConfig(
        raw.getOrDefault("allow", List.of()), raw.getOrDefault("stop", List.of()));
  }
}
