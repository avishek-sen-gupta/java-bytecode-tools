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
    '.traps[] | select(.type | contains("Throwable")) | .handlerBlocks | length == 1' \
    "Throwable (finally) handler has 1 block"

assert_json_contains "$OUT/exception.json" \
    '.traps[] | select(.type | contains("Throwable")) | .coveredBlocks | length > 5' \
    "Throwable (finally) trap covers multiple blocks"

report
