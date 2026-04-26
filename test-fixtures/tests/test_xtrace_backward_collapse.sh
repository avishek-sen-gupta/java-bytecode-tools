#!/usr/bin/env bash
# Test: xtrace --to --collapse produces collapsed backward trace.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace --to --collapse (backward trace)"

$B xtrace --call-graph "$OUT/callgraph.json" \
  --to com.example.app.JdbcOrderRepository --to-line "$FIND_BY_ID_LINE" \
  --collapse \
  --output "$OUT/backward.json" 2>/dev/null

assert_json_field "$OUT/backward.json" '.found' 'true' \
    "found paths"

assert_json_contains "$OUT/backward.json" \
    '.groups | length > 0' \
    "has collapsed groups"

assert_json_contains "$OUT/backward.json" \
    '[.groups[].entryPoints[]] | length > 1' \
    "multiple entry points reach findById"

report
