#!/usr/bin/env bash
# Test: trace (intraprocedural) produces source-level traces.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "trace (intraprocedural)"

$B trace com.example.app.OrderService "$PROCESS_LINE" "$PROCESS_END" \
  > "$OUT/trace.json" 2>/dev/null

assert_json_field "$OUT/trace.json" '.class' 'com.example.app.OrderService' \
    "class"

assert_json_contains "$OUT/trace.json" \
    '.traces | length > 0' \
    "found at least one trace"

assert_json_contains "$OUT/trace.json" \
    '.traces[0].sourceTrace | length > 0' \
    "has sourceTrace entries"

report
