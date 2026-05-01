#!/usr/bin/env bash
# Test: rev-calltree --to-class returns flat {nodes, calls, metadata} backward trace.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "rev-calltree --to-class (backward trace)"

$UV rev-calltree \
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
    '.metadata.tool == "rev-calltree"' \
    "metadata.tool is rev-calltree"

assert_json_contains "$OUT/backward-chains.json" \
    '.metadata.toClass == "com.example.app.JdbcOrderRepository"' \
    "metadata.toClass correct"

assert_json_contains "$OUT/backward-chains.json" \
    '[.nodes | to_entries[].value.class] | any(. == "com.example.app.JdbcOrderRepository")' \
    "target class in nodes"

echo ""
echo "rev-calltree bridge deduplication (covariant return type)"

$UV rev-calltree \
  --call-graph "$OUT/callgraph.json" \
  --to-class com.example.app.CovConcreteDao \
  --to-line "$COV_LOOKUP_LINE" \
  2>/dev/null | tee "$OUT/backward-cov.json" > /dev/null

assert_json_contains "$OUT/backward-cov.json" \
    '.nodes | length > 0' \
    "bridge dedup: nodes present"

report
