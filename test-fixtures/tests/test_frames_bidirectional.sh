#!/usr/bin/env bash
# Test: frames --from-class --to-class finds path between two methods.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "frames --from-class --to-class (bidirectional)"

$UV frames \
  --call-graph "$OUT/callgraph.json" \
  --from-class com.example.app.OrderController \
  --from-line "$HANDLE_GET_LINE" \
  --to-class com.example.app.JdbcOrderRepository \
  --to-line "$FIND_BY_ID_LINE" \
  2>/dev/null | tee "$OUT/bidirectional.json" > /dev/null

assert_json_contains "$OUT/bidirectional.json" \
    '.nodes | length > 0' \
    "nodes present"

assert_json_contains "$OUT/bidirectional.json" \
    '.calls | length > 0' \
    "calls present"

assert_json_contains "$OUT/bidirectional.json" \
    '.metadata.fromClass == "com.example.app.OrderController"' \
    "fromClass in metadata"

assert_json_contains "$OUT/bidirectional.json" \
    '.metadata.toClass == "com.example.app.JdbcOrderRepository"' \
    "toClass in metadata"

assert_json_contains "$OUT/bidirectional.json" \
    '[.nodes | to_entries[].value.class] | any(. == "com.example.app.OrderController")' \
    "from class in nodes"

assert_json_contains "$OUT/bidirectional.json" \
    '[.nodes | to_entries[].value.class] | any(. == "com.example.app.JdbcOrderRepository")' \
    "to class in nodes"

report
