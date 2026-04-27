#!/usr/bin/env bash
# Test: xtrace --from produces a forward call tree.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace --from (forward trace)"

$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.OrderService --from-line "$PROCESS_LINE" \
  --output "$OUT/forward.json" 2>/dev/null

assert_json_field "$OUT/forward.json" '.trace.class' 'com.example.app.OrderService' \
    "root class"

assert_json_field "$OUT/forward.json" '.trace.method' 'processOrder' \
    "root method"

assert_json_contains "$OUT/forward.json" \
    '.trace.children | length > 0' \
    "has children (callees)"

assert_json_contains "$OUT/forward.json" \
    '.trace.sourceTrace | any(.calls | length > 0)' \
    "sourceTrace has call entries"

assert_json_contains "$OUT/forward.json" \
    '.trace.edges | length > 0' \
    "root node has CFG edges"

assert_json_contains "$OUT/forward.json" \
    '.trace.edges | all(has("fromBlock") and has("toBlock"))' \
    "edges have fromBlock and toBlock"

report
