#!/usr/bin/env bash
# Test: dump outputs correct class metadata.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "dump"

assert_json_field "$OUT/dump-svc.json" '.class' 'com.example.app.OrderService' \
    "class name"

assert_json_gt "$OUT/dump-svc.json" '.methodCount' 0 \
    "has methods"

assert_json_contains "$OUT/dump-svc.json" \
    '.methods | any(.method == "processOrder")' \
    "lists processOrder"

assert_json_contains "$OUT/dump-svc.json" \
    '.methods | any(.method == "orderExists")' \
    "lists orderExists"

report
