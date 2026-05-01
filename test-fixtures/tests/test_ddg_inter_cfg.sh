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
  '.nodes | length > 0' \
  "top-level nodes preserved"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.calls | length >= 0' \
  "top-level calls preserved"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.metadata.tool == "ddg-inter-cfg"' \
  "metadata.tool is ddg-inter-cfg"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.ddgs | length > 0' \
  "ddgs map present"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '.ddgs["<com.example.app.OrderService: java.lang.String processOrder(int)>"].nodes | length > 0' \
  "statement nodes present for processOrder"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '[.ddgs["<com.example.app.OrderService: java.lang.String processOrder(int)>"].edges[].edge_info.kind] | any(. == "cfg")' \
  "cfg edges present"

assert_json_contains "$OUT/ddg-inter-cfg.json" \
  '[.ddgs["<com.example.app.OrderService: java.lang.String processOrder(int)>"].edges[].edge_info.kind] | any(. == "ddg")' \
  "ddg edges present"

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
