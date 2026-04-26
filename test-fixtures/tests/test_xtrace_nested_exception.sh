#!/usr/bin/env bash
# Test: xtrace --from handles nested exception traps.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace --from (nested exception handling)"

$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.NestedExceptionService --from-line "$NESTED_LINE" \
  --output "$OUT/nested.json" 2>/dev/null

assert_json_field "$OUT/nested.json" '.method' 'nestedHandle' \
    "method name"

assert_json_contains "$OUT/nested.json" \
    '.traps | length == 2' \
    "has exactly 2 traps (inner + outer)"

# Verify inner catch: 6 handler blocks (excludes normal-flow exit B9 and method return B16)
assert_json_contains "$OUT/nested.json" \
    '.traps[] | select(.type | contains("java.lang.Exception")) | .handlerBlocks | length == 6' \
    "inner Exception handler has 6 blocks (excludes merge points)"

# Verify outer catch: 1 handler block (excludes method return B16)
assert_json_contains "$OUT/nested.json" \
    '.traps[] | select(.type | contains("RuntimeException")) | .handlerBlocks | length == 1' \
    "outer RuntimeException handler has 1 block (excludes method return)"

report
