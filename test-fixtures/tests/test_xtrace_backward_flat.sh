#!/usr/bin/env bash
# Test: xtrace --to --collapse --flat produces smaller output than full.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace --to --collapse --flat (flat backward trace)"

# Need full output for comparison
$B xtrace --call-graph "$OUT/callgraph.json" \
  --to com.example.app.JdbcOrderRepository --to-line "$FIND_BY_ID_LINE" \
  --collapse \
  --output "$OUT/backward-full.json" 2>/dev/null

$B xtrace --call-graph "$OUT/callgraph.json" \
  --to com.example.app.JdbcOrderRepository --to-line "$FIND_BY_ID_LINE" \
  --collapse --flat \
  --output "$OUT/backward-flat.json" 2>/dev/null

assert_json_field "$OUT/backward-flat.json" '.found' 'true' \
    "found paths"

assert_json_contains "$OUT/backward-flat.json" \
    '.groups | length > 0' \
    "has collapsed groups"

assert_file_smaller "$OUT/backward-flat.json" "$OUT/backward-full.json" \
    "flat output smaller than full"

report
