#!/usr/bin/env bash
# Test: buildcg produces a valid call graph with expected edges.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "buildcg"

assert_json_gt "$OUT/callgraph.json" '. | length' 0 \
    "call graph has edges"

assert_json_contains "$OUT/callgraph.json" \
    'to_entries | any(.value[] | test("findById"))' \
    "call graph contains findById callee"

report
