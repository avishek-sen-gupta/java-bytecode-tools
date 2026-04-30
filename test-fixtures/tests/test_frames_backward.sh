#!/usr/bin/env bash
# Test: frames --to-class returns flat {nodes, calls, metadata} backward trace.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "frames --to-class (backward trace)"

$UV frames \
  --call-graph "$OUT/callgraph.json" \
  --to-class com.example.app.JdbcOrderRepository \
  --to-line "$FIND_BY_ID_LINE" \
  2>/dev/null | tee "$OUT/backward-chains.json" > /dev/null

assert_json_contains "$OUT/backward-chains.json" \
    '.nodes | length > 0' \
    "nodes present"

assert_json_contains "$OUT/backward-chains.json" \
    '.calls | length > 0' \
    "calls present"

assert_json_contains "$OUT/backward-chains.json" \
    '.metadata.tool == "frames"' \
    "metadata.tool is frames"

assert_json_contains "$OUT/backward-chains.json" \
    '.metadata.toClass == "com.example.app.JdbcOrderRepository"' \
    "metadata.toClass correct"

assert_json_contains "$OUT/backward-chains.json" \
    '[.nodes | to_entries[].value.class] | any(. == "com.example.app.JdbcOrderRepository")' \
    "target class in nodes"

echo ""
echo "frames bridge deduplication (covariant return type)"

$UV frames \
  --call-graph "$OUT/callgraph.json" \
  --to-class com.example.app.CovConcreteDao \
  --to-line "$COV_LOOKUP_LINE" \
  2>/dev/null | tee "$OUT/backward-cov.json" > /dev/null

assert_json_contains "$OUT/backward-cov.json" \
    '.nodes | length > 0' \
    "bridge dedup: nodes present"

report
