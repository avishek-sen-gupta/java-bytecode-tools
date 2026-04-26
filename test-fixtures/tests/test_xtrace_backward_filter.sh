#!/usr/bin/env bash
# Test: xtrace --to respects --filter.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace --to (backward filter)"

$B xtrace --call-graph "$OUT/callgraph.json" \
  --to com.example.app.OrderService --to-line "$PROCESS_LINE" \
  --filter "$FIXTURE/filter-stop.json" \
  --output "$OUT/backward_filtered.json" 2>/dev/null

# The filter stops at com.example.app, so all frames in this chain are filtered
assert_json_contains "$OUT/backward_filtered.json" \
    '.chains[0] | all(.[]; .filtered == true)' \
    "all frames are filtered (all in com.example.app)"

assert_json_contains "$OUT/backward_filtered.json" \
    '.chains[0] | all(.[]; .blocks == null)' \
    "no filtered frame has blocks"

assert_json_contains "$OUT/backward_filtered.json" \
    '.chains[0] | all(.[]; .traps == null)' \
    "no filtered frame has traps"

report
