#!/usr/bin/env bash
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "ddg-inter-cfg stdin -> stdout"

$UV fw-calltree \
  --callgraph "$OUT/callgraph.json" \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  | $B ddg-inter-cfg 2>/dev/null | tee "$OUT/ddg-inter-cfg.json" > /dev/null

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.calltree.nodes | length > 0' \
  "calltree nodes present"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.calltree.edges | length >= 0' \
  "calltree edges present"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.metadata.tool == "ddg-inter-cfg"' \
  "metadata.tool is ddg-inter-cfg"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.ddg.nodes | length > 0' \
  "ddg statement nodes present"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '[.ddg.edges[].edge_info.kind] | any(. == "LOCAL")' \
  "local edges present"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.ddg.edges | length > 0' \
  "edges are populated"

echo ""
echo "ddg-inter-cfg --input/--output"

$UV fw-calltree \
  --callgraph "$OUT/callgraph.json" \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  > "$OUT/fw-calltree.json"

$B ddg-inter-cfg \
  --input "$OUT/fw-calltree.json" \
  --output "$OUT/ddg-inter-cfg-file.json" 2>/dev/null

assert_json_contains "$OUT/ddg-inter-cfg-file.json" \
  '.metadata.inputTool == "calltree"' \
  "inputTool copied from fw-calltree metadata"

echo ""
echo "ddg-inter-cfg invalid input"

printf '{\n  "calls": []\n}\n' > "$OUT/invalid-fw-calltree.json"

if $B ddg-inter-cfg --input "$OUT/invalid-fw-calltree.json" > "$OUT/invalid.log" 2>&1; then
  fail "invalid input exits non-zero" "command unexpectedly succeeded"
else
  pass "invalid input exits non-zero"
fi

assert_file_contains "$OUT/invalid.log" "nodes" "invalid input mentions missing nodes"

report
