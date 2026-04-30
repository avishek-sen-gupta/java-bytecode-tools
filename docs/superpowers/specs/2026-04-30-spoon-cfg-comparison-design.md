# Spoon CFG Comparison Experiment

**Date:** 2026-04-30
**Status:** Approved

## Goal

Compare Spoon's source-level CFG against SootUp's bytecode-level CFG for the same method, to evaluate whether Spoon provides richer information (source positions, original variable names, declared types) sufficient to replace SootUp across the analysis pipeline.

## Scope

This is an experiment, not a feature. No production code is added. If Spoon wins, a follow-up spec covers the replacement.

## Dependencies

Two new `test`-scoped additions to `java/pom.xml`:

- `fr.inria.gforge.spoon:spoon-core` — Spoon AST/model; parses `.java` source files
- `fr.inria.gforge.spoon:spoon-control-flow` — `ControlFlowBuilder` + `ControlFlowGraph` over Spoon AST

No production dependency changes. SootUp remains untouched.

## Test

**Class:** `java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java`

**Method under test:** `com.example.app.OrderService.processOrder` (source at `test-fixtures/src/`, classes at `test-fixtures/classes/`)

**Steps:**

1. **SootUp side** — construct `BytecodeTracer` with `test-fixtures/classes`, resolve `processOrder` via `resolveMethodByName`, walk `StmtGraph` nodes
2. **Spoon side** — construct `Launcher` with `test-fixtures/src` as source path, find `processOrder` via `CtMethod`, run `ControlFlowBuilder`, walk `ControlFlowGraph` nodes
3. **Print side-by-side comparison** to stdout — for each CFG node matched by source line:
   ```
   === Node 3 ===
   SOOTUP : $r2 = virtualinvoke $r1.<...OrderService: String transform(String)>(...)  [line 21]
   SPOON  : String result = transform(order)                                           [line 21, col 9]
            vars: result (String), order (String)
   ```
   Unmatched nodes (synthetic SootUp assignments, etc.) printed with `(no match)` on the other side.
4. **Summary line:** total nodes in each CFG, count matched by line.
5. **Generate DOT + SVG** for both CFGs:
   - Build DOT string (nodes = statement text, edges = control flow)
   - Write to `target/sootup-cfg.dot` and `target/spoon-cfg.dot`
   - Shell out: `dot -Tsvg -o target/sootup-cfg.svg target/sootup-cfg.dot`
   - Shell out: `dot -Tsvg -o target/spoon-cfg.svg target/spoon-cfg.dot`
   - SVGs written to `target/` (gitignored)

**No assertions.** The test always passes. Output is read by the developer to form a judgment.

## Running

```bash
cd java && mvn test -Dtest=SpoonCfgComparisonTest
# SVGs at: java/target/sootup-cfg.svg, java/target/spoon-cfg.svg
```

## Success Criteria

The experiment is complete when:
- Both CFGs are printed to stdout without errors
- Both SVGs are written and renderable
- The developer can directly compare node labels, positions, and variable names

## What to Evaluate

| Dimension | SootUp (bytecode) | Spoon (source) |
|-----------|-------------------|----------------|
| Statement text | Jimple SSA form (`$r2 = virtualinvoke ...`) | Original source (`String result = transform(order)`) |
| Source position | Line number only | File + line + column |
| Variable names | SSA-renamed (`$r1`, `$i0`) | Original names (`order`, `id`) |
| Types | Fully qualified Jimple types | Declared source types |

## Files Changed

- `java/pom.xml` — add two test-scoped Spoon dependencies
- `java/src/test/java/tools/bytecode/SpoonCfgComparisonTest.java` — new test class
