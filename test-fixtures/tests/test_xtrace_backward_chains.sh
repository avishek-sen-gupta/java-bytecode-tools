#!/usr/bin/env bash
# Test: xtrace --to without --collapse returns raw chains.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace --to (backward, no collapse)"

$B xtrace --call-graph "$OUT/callgraph.json" \
  --to com.example.app.JdbcOrderRepository --to-line "$FIND_BY_ID_LINE" \
  --output "$OUT/backward-chains.json" 2>/dev/null

assert_json_field "$OUT/backward-chains.json" '.found' 'true' \
    "found"

assert_json_contains "$OUT/backward-chains.json" \
    '.chains | length > 0' \
    "has chain list"

report
