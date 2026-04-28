#!/usr/bin/env bash
# Test: frames --to returns lightweight nested chain trees.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "frames --to (backward trace, lightweight chains)"

$B frames --call-graph "$OUT/callgraph.json" \
  --to com.example.app.JdbcOrderRepository --to-line "$FIND_BY_ID_LINE" \
  --output "$OUT/backward-chains.json" 2>/dev/null

assert_json_field "$OUT/backward-chains.json" '.found' 'true' \
    "found"

assert_json_contains "$OUT/backward-chains.json" \
    '.trace.children | length > 0' \
    "has chain trees under synthetic root"

assert_json_contains "$OUT/backward-chains.json" \
    '.trace.synthetic == true' \
    "root is marked synthetic"

assert_json_contains "$OUT/backward-chains.json" \
    '.trace.children[0] | has("class")' \
    "chain tree nodes have class field"

assert_json_contains "$OUT/backward-chains.json" \
    '.trace.children[0] | has("lineStart")' \
    "chain tree nodes have lineStart"

assert_json_contains "$OUT/backward-chains.json" \
    '.trace.children[0].blocks == null' \
    "lightweight frames have no blocks"

report
