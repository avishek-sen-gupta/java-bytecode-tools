package tools.source.icfg;

import java.util.Arrays;
import java.util.function.Predicate;

public interface StopCondition extends Predicate<String> {

  static StopCondition exact(String fqn) {
    return s -> s.equals(fqn);
  }

  static StopCondition prefix(String namespace) {
    return s -> s.startsWith(namespace);
  }

  static StopCondition any(StopCondition... conditions) {
    return s -> Arrays.stream(conditions).anyMatch(c -> c.test(s));
  }

  static StopCondition none() {
    return s -> false;
  }
}
