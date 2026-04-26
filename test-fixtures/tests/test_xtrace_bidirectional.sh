#!/usr/bin/env bash
# Test: xtrace --from --to (bidirectional) finds path between two methods.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace --from --to (bidirectional)"

$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.OrderController --from-line "$HANDLE_GET_LINE" \
  --to com.example.app.JdbcOrderRepository --to-line "$FIND_BY_ID_LINE" \
  --collapse \
  --output "$OUT/bidirectional.json" 2>/dev/null

assert_json_field "$OUT/bidirectional.json" '.found' 'true' \
    "found path"

assert_json_contains "$OUT/bidirectional.json" \
    '.groups[0].entryPoints[] | select(. == "com.example.app.OrderController.handleGet")' \
    "entry point is OrderController.handleGet"

assert_json_contains "$OUT/bidirectional.json" \
    '.groups[0].chain | length == 2' \
    "chain has 2 hops (processOrder → findById)"

assert_json_field "$OUT/bidirectional.json" \
    '.groups[0].chain[-1].method' 'findById' \
    "chain ends at findById"

report
