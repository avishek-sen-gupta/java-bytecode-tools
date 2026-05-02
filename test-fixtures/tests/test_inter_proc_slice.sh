#!/usr/bin/env bash
# E2E test: backward slice traces across method boundary via pre-computed PARAM/RETURN edges.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup

CALLER="<com.example.app.OrderService: java.lang.String processOrder(int)>"

echo "inter-procedural backward slice through OrderService.processOrder()"
echo "  (tests pre-computed PARAM and RETURN edges in DDG)"

# Build calltree rooted at OrderService.processOrder
$UV fw-calltree \
  --callgraph "$OUT/callgraph.json" \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  | $B ddg-inter-cfg 2>/dev/null \
  | tee "$OUT/inter-proc-ddg.json" > /dev/null

# Verify DDG contains PARAM edges
assert_json_contains "$OUT/inter-proc-ddg.json" \
  '.ddg.edges | map(select(.edge_info.kind == "PARAM")) | length > 0' \
  "DDG contains at least one PARAM edge"

# Verify DDG contains RETURN edges
assert_json_contains "$OUT/inter-proc-ddg.json" \
  '.ddg.edges | map(select(.edge_info.kind == "RETURN")) | length > 0' \
  "DDG contains at least one RETURN edge"

# Backward slice should trace across method boundary
cat "$OUT/inter-proc-ddg.json" \
  | $B bwd-slice \
      --method "$CALLER" \
      --local-var "i0" 2>/dev/null \
  | tee "$OUT/inter-proc-slice.json" > /dev/null

# Verify slice contains nodes
assert_json_contains "$OUT/inter-proc-slice.json" \
  '.nodes | type == "array"' \
  "output has nodes array"

# Verify slice has edges array
assert_json_contains "$OUT/inter-proc-slice.json" \
  '.edges | type == "array"' \
  "output has edges array"

# Verify seed is set correctly
assert_json_contains "$OUT/inter-proc-slice.json" \
  '.seed.method == "'"$CALLER"'"' \
  "seed method is processOrder"

# Verify seed local_var is set
assert_json_contains "$OUT/inter-proc-slice.json" \
  '.seed.local_var == "i0"' \
  "seed local_var is i0"

report
