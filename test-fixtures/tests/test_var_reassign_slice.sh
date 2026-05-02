#!/usr/bin/env bash
# E2E test: backward slice through variable reassignment.
# Verifies that DDG edge building correctly follows reaching definitions through
# non-SSA Jimple (unversioned locals, produced by methods with conditional branches).
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup

METHOD="<com.example.app.VarReassignService: java.lang.String sanitize(java.lang.String)>"

echo "backward slice from 'value' local in VarReassignService.sanitize()"
echo "  (tests reaching-definition edges through conditional-branch non-SSA Jimple)"

# Create a minimal call graph with just VarReassignService.sanitize()
# (it's not reachable from any entry point, so we construct it manually)
cat > "$OUT/var-reassign-calltree.json" <<'EOF'
{
  "nodes": {
    "<com.example.app.VarReassignService: java.lang.String sanitize(java.lang.String)>": {
      "node_type": "java_method",
      "class": "com.example.app.VarReassignService",
      "method": "sanitize",
      "methodSignature": "<com.example.app.VarReassignService: java.lang.String sanitize(java.lang.String)>"
    }
  },
  "calls": [],
  "metadata": {
    "root": "<com.example.app.VarReassignService: java.lang.String sanitize(java.lang.String)>"
  }
}
EOF

# Build backward slice from the reassigned 'value' variable (unversioned - conditional branch)
cat "$OUT/var-reassign-calltree.json" \
  | $B ddg-inter-cfg 2>/dev/null \
  | $B bwd-slice \
      --method "$METHOD" \
      --local-var "value" 2>/dev/null \
  | tee "$OUT/var-reassign-slice.json" > /dev/null

# Verify slice contains nodes
assert_json_contains "$OUT/var-reassign-slice.json" \
  '.nodes | type == "array"' \
  "output has nodes array"

# Verify slice contains edges
assert_json_contains "$OUT/var-reassign-slice.json" \
  '.edges | type == "array"' \
  "output has edges array"

# Verify slice has at least one edge (param -> reassignment)
assert_json_contains "$OUT/var-reassign-slice.json" \
  '.edges | length > 0' \
  "slice contains at least one reaching-definition edge"

# Verify the method in seed
assert_json_contains "$OUT/var-reassign-slice.json" \
  '.seed.method == "'"$METHOD"'"' \
  "seed method is sanitize"

# Verify the local in seed
assert_json_contains "$OUT/var-reassign-slice.json" \
  '.seed.local_var == "value"' \
  "seed local_var is value"

# Verify all edges have kind information
assert_json_contains "$OUT/var-reassign-slice.json" \
  '[.edges[].edge_info.kind] | all(. != null)' \
  "all edges have edge_info.kind"

report
