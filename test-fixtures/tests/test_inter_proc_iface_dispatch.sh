#!/usr/bin/env bash
# E2E test: backward slice through interface-dispatched call.
# Verifies that PARAM/RETURN edges are generated when calltree uses concrete
# class signature but Jimple call site uses interface signature.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup

CALLER="<com.example.app.OrderService: java.lang.String processOrder(int)>"
CALLEE="<com.example.app.JdbcOrderRepository: java.lang.String findById(int)>"

echo "backward slice through interface-dispatched call"
echo "  OrderService.processOrder -> JdbcOrderRepository.findById"

cat > "$OUT/iface-dispatch-calltree.json" <<EOF
{
  "nodes": {
    "$CALLER": {
      "node_type": "java_method",
      "class": "com.example.app.OrderService",
      "method": "processOrder",
      "methodSignature": "$CALLER"
    },
    "$CALLEE": {
      "node_type": "java_method",
      "class": "com.example.app.JdbcOrderRepository",
      "method": "findById",
      "methodSignature": "$CALLEE"
    }
  },
  "calls": [
    {
      "from": "$CALLER",
      "to": "$CALLEE"
    }
  ],
  "metadata": {
    "root": "$CALLER"
  }
}
EOF

# Build DDG and verify inter-proc edges exist
cat "$OUT/iface-dispatch-calltree.json" \
  | $B ddg-inter-cfg 2>/dev/null \
  | tee "$OUT/iface-dispatch-ddg.json" > /dev/null

# Verify PARAM edges exist (interface dispatch bridged)
assert_json_contains "$OUT/iface-dispatch-ddg.json" \
  '[.ddg.edges[].edge_info.kind] | any(. == "PARAM")' \
  "DDG contains PARAM edges for interface-dispatched call"

# Verify RETURN edges exist
assert_json_contains "$OUT/iface-dispatch-ddg.json" \
  '[.ddg.edges[].edge_info.kind] | any(. == "RETURN")' \
  "DDG contains RETURN edges for interface-dispatched call"

# Backward slice from findById's parameter
cat "$OUT/iface-dispatch-calltree.json" \
  | $B ddg-inter-cfg 2>/dev/null \
  | $B bwd-slice \
      --method "$CALLEE" \
      --local-var "id" 2>/dev/null \
  | tee "$OUT/iface-dispatch-slice.json" > /dev/null

# Verify slice has nodes
assert_json_contains "$OUT/iface-dispatch-slice.json" \
  '.nodes | length > 0' \
  "slice has nodes"

# Verify slice has edges
assert_json_contains "$OUT/iface-dispatch-slice.json" \
  '.edges | length > 0' \
  "slice has edges"

# Verify slice contains PARAM edge (the inter-proc connection)
assert_json_contains "$OUT/iface-dispatch-slice.json" \
  '[.edges[].edge_info.kind] | any(. == "PARAM")' \
  "slice traces through PARAM edge across interface dispatch"

report
