#!/usr/bin/env bash
# Test: ftrace-slice + ftrace-expand-refs pipeline.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "ftrace-slice + ftrace-expand-refs pipeline"

# Generate a trace that has refs
$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.ComplexService --from-line "$COMPLEX_LINE" \
  --output "$OUT/complex.json"

# Slice out handleException (now outputs SlicedTrace)
cd "$REPO_ROOT/python"
uv run ftrace-slice --input "$OUT/complex.json" \
  --query '.children[] | select(.method == "handleException")' \
  --output "$OUT/sliced.json"

assert_json_contains "$OUT/sliced.json" \
    '.slice | .method == "handleException"' \
    "sliced root method in .slice"

assert_json_contains "$OUT/sliced.json" \
    '.refIndex | length >= 0' \
    "has refIndex field"

# Expand refs (produces plain trace node)
uv run ftrace-expand-refs --input "$OUT/sliced.json" \
  --output "$OUT/expanded.json"

assert_json_field "$OUT/expanded.json" '.method' 'handleException' \
    "expanded root method"

assert_json_contains "$OUT/expanded.json" \
    '.blocks | length > 0' \
    "has blocks after expansion"

assert_json_contains "$OUT/expanded.json" \
    '.traps | length == 2' \
    "has traps after expansion"

assert_json_contains "$OUT/expanded.json" \
    '.traps[] | select(.type | contains("RuntimeException")) | .handlerBlocks | length == 4' \
    "RuntimeException handler has 4 blocks (no normal-flow leakage)"

# Full pipeline: expanded → semantic → dot
uv run ftrace-semantic --input "$OUT/expanded.json" --output "$OUT/sliced-semantic.json"

assert_json_contains "$OUT/sliced-semantic.json" \
    '.nodes | length > 0' \
    "sliced semantic graph has nodes"

uv run ftrace-to-dot --input "$OUT/sliced-semantic.json" --output "$OUT/sliced-pipeline.dot"

assert_file_contains "$OUT/sliced-pipeline.dot" "digraph" \
    "sliced DOT output is a digraph"

# Fully piped: cat | slice | expand-refs | semantic | to-dot (all stdin/stdout)
cat "$OUT/complex.json" \
  | uv run ftrace-slice --query '.children[] | select(.method == "handleException")' \
  | uv run ftrace-expand-refs \
  | uv run ftrace-semantic \
  | uv run ftrace-to-dot > "$OUT/piped.dot"

assert_file_contains "$OUT/piped.dot" "digraph" \
    "piped pipeline produces a digraph"

assert_file_contains "$OUT/piped.dot" "handleException" \
    "piped pipeline DOT contains handleException"

# End-to-end piped: xtrace | slice | expand-refs | semantic | to-dot (no intermediate files)
$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.ComplexService --from-line "$COMPLEX_LINE" \
  | uv run ftrace-slice --query '.children[] | select(.method == "handleException")' \
  | uv run ftrace-expand-refs \
  | uv run ftrace-semantic \
  | uv run ftrace-to-dot > "$OUT/e2e-piped.dot"

assert_file_contains "$OUT/e2e-piped.dot" "digraph" \
    "e2e piped from xtrace produces a digraph"

assert_file_contains "$OUT/e2e-piped.dot" "handleException" \
    "e2e piped from xtrace contains handleException"

report
