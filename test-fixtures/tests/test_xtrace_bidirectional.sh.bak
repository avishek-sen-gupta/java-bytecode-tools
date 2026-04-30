#!/usr/bin/env bash
# Test: frames --from --to (bidirectional) finds path between two methods.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "frames --from --to (bidirectional)"

$B frames --call-graph "$OUT/callgraph.json" \
  --from com.example.app.OrderController --from-line "$HANDLE_GET_LINE" \
  --to com.example.app.JdbcOrderRepository --to-line "$FIND_BY_ID_LINE" \
  --output "$OUT/bidirectional.json" 2>/dev/null

assert_json_field "$OUT/bidirectional.json" '.found' 'true' \
    "found path"

assert_json_contains "$OUT/bidirectional.json" \
    '.trace.synthetic == true' \
    "result has synthetic root"

assert_json_contains "$OUT/bidirectional.json" \
    '.trace.children | length > 0' \
    "has at least one chain"

assert_json_contains "$OUT/bidirectional.json" \
    '.trace.children[0].class == "com.example.app.OrderController"' \
    "chain starts at OrderController"

assert_json_contains "$OUT/bidirectional.json" \
    '.fromClass == "com.example.app.OrderController"' \
    "fromClass recorded in result"

report
