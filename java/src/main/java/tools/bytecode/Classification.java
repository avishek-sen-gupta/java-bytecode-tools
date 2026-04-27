package tools.bytecode;

/** Classification of a method encountered during call graph discovery. */
public enum Classification {
  NORMAL,
  CYCLE,
  FILTERED
}
