#!/usr/bin/env bash
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

READ_METHOD="<com.example.app.FieldProvenanceService: int read()>"
UPDATE_METHOD="<com.example.app.FieldProvenanceService: void update(int)>"

echo "field provenance: bwd-slice follows heap edges through field read/write"

$UV fw-calltree \
  --callgraph "$OUT/callgraph.json" \
  --class com.example.app.FieldProvenanceService \
  --method caller \
  --pattern 'com\.example' \
  | $B ddg-inter-cfg --unbounded 2>/dev/null \
  | tee "$OUT/field-provenance-ddg.json" > /dev/null

cat "$OUT/field-provenance-ddg.json" \
  | $B bwd-slice \
      --method "$READ_METHOD" \
      --local-var "value" 2>/dev/null \
  | tee "$OUT/field-provenance-slice.json" > /dev/null

assert_json_contains "$OUT/field-provenance-slice.json" \
  '.nodes | type == "array"' \
  "output has nodes array"

assert_json_contains "$OUT/field-provenance-slice.json" \
  '.edges | type == "array"' \
  "output has edges array"

assert_json_contains "$OUT/field-provenance-slice.json" \
  '.seed.method == "'"$READ_METHOD"'"' \
  "seed method is read"

assert_json_contains "$OUT/field-provenance-slice.json" \
  '[.edges[].edge_info.kind] | contains(["HEAP"])' \
  "at least one HEAP edge in output"

assert_json_contains "$OUT/field-provenance-slice.json" \
  '[.edges[].edge_info.kind] | contains(["LOCAL"])' \
  "at least one LOCAL edge in output"

report
