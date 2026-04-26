#!/usr/bin/env bash
# Test: xtrace --from --filter stops recursion at filtered classes.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace --from --filter (filtered forward trace)"

$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.OrderService --from-line "$PROCESS_LINE" \
  --filter "$FIXTURE/filter.json" \
  --output "$OUT/forward-filtered.json" 2>/dev/null

assert_json_contains "$OUT/forward-filtered.json" \
    '.. | objects | select(.filtered? == true) | .class' \
    "has filtered leaf nodes"

report
