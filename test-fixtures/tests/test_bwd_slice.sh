#!/usr/bin/env bash
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

METHOD="<com.example.app.OrderService: java.lang.String processOrder(int)>"

echo "bwd-slice stdin -> stdout pipeline"

$UV fw-calltree \
  --callgraph "$OUT/callgraph.json" \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  | $B ddg-inter-cfg 2>/dev/null \
  | $B bwd-slice \
      --method "$METHOD" \
      --local-var "i0" 2>/dev/null \
  | tee "$OUT/bwd-slice.json" > /dev/null

assert_json_contains "$OUT/bwd-slice.json" \
  '.nodes | type == "array"' \
  "output has nodes array"

assert_json_contains "$OUT/bwd-slice.json" \
  '.edges | type == "array"' \
  "output has edges array"

assert_json_contains "$OUT/bwd-slice.json" \
  '.seed | has("method") and has("local_var")' \
  "seed has method and local_var fields"

assert_json_contains "$OUT/bwd-slice.json" \
  '[.edges[].edge_info.kind] | all(. != null)' \
  "all edges have edge_info.kind"

assert_json_contains "$OUT/bwd-slice.json" \
  '.seed.method == "'"$METHOD"'"' \
  "seed method is processOrder"

assert_json_contains "$OUT/bwd-slice.json" \
  '.seed.local_var == "i0"' \
  "seed local_var is i0"

echo ""
echo "bwd-slice --input/--output file mode"

$UV fw-calltree \
  --callgraph "$OUT/callgraph.json" \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  | $B ddg-inter-cfg 2>/dev/null > "$OUT/ddg-inter-cfg.json"

$B bwd-slice \
  --input "$OUT/ddg-inter-cfg.json" \
  --output "$OUT/bwd-slice-file.json" \
  --method "$METHOD" \
  --local-var "i0" 2>/dev/null

assert_json_contains "$OUT/bwd-slice-file.json" \
  '.nodes | type == "array"' \
  "file-mode output has nodes array"

echo ""
echo "bwd-slice missing local returns empty result"

$B bwd-slice \
  --input "$OUT/ddg-inter-cfg.json" \
  --output "$OUT/bwd-slice-empty.json" \
  --method "$METHOD" \
  --local-var "__nonexistent__" 2>/dev/null

assert_json_contains "$OUT/bwd-slice-empty.json" \
  '.nodes | length == 0' \
  "nonexistent local yields empty nodes"

assert_json_contains "$OUT/bwd-slice-empty.json" \
  '.edges | length == 0' \
  "nonexistent local yields empty edges"

report
