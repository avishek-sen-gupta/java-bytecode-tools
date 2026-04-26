#!/usr/bin/env bash
# Test: xtrace --from handles exception traps and clusters.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace --from (exception handling)"

$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.ExceptionService --from-line "$EXCEPTION_LINE" \
  --output "$OUT/exception.json" 2>/dev/null

assert_json_field "$OUT/exception.json" '.method' 'handleException' \
    "method name"

assert_json_contains "$OUT/exception.json" \
    '.traps | length == 2' \
    "has 2 traps (catch + finally)"

assert_json_contains "$OUT/exception.json" \
    '.traps[] | select(.type | contains("RuntimeException")) | .handlerBlocks | length == 4' \
    "RuntimeException handler has 4 blocks (excludes method return)"

assert_json_contains "$OUT/exception.json" \
    '.traps[] | select(.type | contains("Throwable")) | .handlerBlocks | length == 2' \
    "Throwable (finally) handler has 2 blocks (exception-path + inlined normal-path)"

assert_json_contains "$OUT/exception.json" \
    '.traps[] | select(.type | contains("Throwable")) | .coveredBlocks | length > 5' \
    "Throwable (finally) trap covers multiple blocks"

# Gap-fill: intermediate blocks (B3, B5) must appear in RuntimeException coveredBlocks
assert_json_contains "$OUT/exception.json" \
    '.traps[] | select(.type | contains("RuntimeException")) | .coveredBlocks | index("B3")' \
    "gap-fill: B3 (intermediate L9) in RuntimeException coveredBlocks"

assert_json_contains "$OUT/exception.json" \
    '.traps[] | select(.type | contains("RuntimeException")) | .coveredBlocks | index("B5")' \
    "gap-fill: B5 (intermediate L9) in RuntimeException coveredBlocks"

# Normal-path finally (B13) must NOT be in any trap's coveredBlocks
assert_json_contains "$OUT/exception.json" \
    '[.traps[].coveredBlocks[] | select(. == "B13")] | length == 0' \
    "B13 (normal-path finally) not in any coveredBlocks"

# B13 (inlined finally) should be in Throwable's handlerBlocks
assert_json_contains "$OUT/exception.json" \
    '.traps[] | select(.type | contains("Throwable")) | .handlerBlocks | index("B13")' \
    "B13 (inlined finally) in Throwable handlerBlocks"

# B0 (entry block L6) should be in a trap's coveredBlocks
assert_json_contains "$OUT/exception.json" \
    '[.traps[].coveredBlocks[] | select(. == "B0")] | length > 0' \
    "B0 (entry block) in coveredBlocks via gap-fill"

# Pipeline: raw → semantic → dot
cd "$REPO_ROOT/python"
uv run ftrace-semantic --input "$OUT/exception.json" --output "$OUT/exception-semantic.json" 2>/dev/null

assert_json_contains "$OUT/exception-semantic.json" \
    '.nodes | length > 0' \
    "semantic graph has nodes"

assert_json_contains "$OUT/exception-semantic.json" \
    '.clusters | length == 4' \
    "semantic graph has 4 clusters (2 traps x try+handler)"

uv run ftrace-to-dot --input "$OUT/exception-semantic.json" --output "$OUT/exception.dot" 2>/dev/null

assert_file_contains "$OUT/exception.dot" "digraph" \
    "DOT output is a digraph"

report
