#!/usr/bin/env bash
# Test: ftrace-slice (python) can slice and expand a trace.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "ftrace-slice (python)"

# Generate a trace that has refs
$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.ComplexService --from-line "$COMPLEX_LINE" \
  --output "$OUT/complex.json" 2>/dev/null

# Slice out handleException
cd "$REPO_ROOT/python"
uv run ftrace-slice --input "$OUT/complex.json" \
  --query '.children[] | select(.method == "handleException")' \
  --output "$OUT/sliced.json" 2>/dev/null

assert_json_field "$OUT/sliced.json" '.method' 'handleException' \
    "sliced root method"

assert_json_contains "$OUT/sliced.json" \
    '.blocks | length > 0' \
    "has blocks after expansion"

assert_json_contains "$OUT/sliced.json" \
    '.traps | length == 2' \
    "has traps after expansion"

assert_json_contains "$OUT/sliced.json" \
    '.traps[] | select(.type | contains("RuntimeException")) | .handlerBlocks | length == 4' \
    "RuntimeException handler has 4 blocks (no normal-flow leakage)"

# Pipeline: sliced raw → semantic → dot
uv run ftrace-semantic --input "$OUT/sliced.json" --output "$OUT/sliced-semantic.json" 2>/dev/null

assert_json_contains "$OUT/sliced-semantic.json" \
    '.nodes | length > 0' \
    "sliced semantic graph has nodes"

uv run ftrace-to-dot --input "$OUT/sliced-semantic.json" --output "$OUT/sliced-pipeline.dot" 2>/dev/null

assert_file_contains "$OUT/sliced-pipeline.dot" "digraph" \
    "sliced DOT output is a digraph"

report
