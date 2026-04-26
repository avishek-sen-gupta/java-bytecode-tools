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

report
