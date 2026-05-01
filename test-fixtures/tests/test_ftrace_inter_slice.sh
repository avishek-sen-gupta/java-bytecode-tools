#!/usr/bin/env bash
# Test: ftrace-inter-slice + ftrace-expand-refs pipeline.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "ftrace-inter-slice + ftrace-expand-refs pipeline"

# Generate a trace that has refs
$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.ComplexService --from-line "$COMPLEX_LINE" \
  --output "$OUT/complex.json"

# Slice out handleException (now outputs SlicedTrace)
$UV ftrace-inter-slice --input "$OUT/complex.json" \
  --from com.example.app.ExceptionService \
  --output "$OUT/sliced.json"

assert_json_contains "$OUT/sliced.json" \
    '.trace | .method == "handleException"' \
    "sliced root method in .trace"

assert_json_contains "$OUT/sliced.json" \
    '.refIndex | length >= 0' \
    "has refIndex field"

# Expand refs (produces plain trace node)
$UV ftrace-expand-refs --input "$OUT/sliced.json" \
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

# --to only: prune from trace root to target class
$UV ftrace-inter-slice --input "$OUT/complex.json" \
  --to com.example.app.ExceptionService \
  --output "$OUT/sliced-to.json"

assert_json_contains "$OUT/sliced-to.json" \
    '.trace | .class == "com.example.app.ComplexService"' \
    "--to: trace root is ComplexService (trace root)"

assert_json_contains "$OUT/sliced-to.json" \
    '.trace.children | length == 1' \
    "--to: one path reaches ExceptionService"

assert_json_contains "$OUT/sliced-to.json" \
    '.trace.children[0] | .class == "com.example.app.ExceptionService"' \
    "--to: child is ExceptionService"

assert_json_contains "$OUT/sliced-to.json" \
    '.trace.children[0].children | length == 0' \
    "--to: ExceptionService is a leaf (children stripped)"

assert_json_contains "$OUT/sliced-to.json" \
    '.refIndex | length == 1' \
    "--to: refIndex populated for ref node"

# --from + --to: find subtree at --from, prune to paths reaching --to
$UV ftrace-inter-slice --input "$OUT/complex.json" \
  --from com.example.app.ComplexService \
  --to com.example.app.ExceptionService \
  --output "$OUT/sliced-from-to.json"

assert_json_contains "$OUT/sliced-from-to.json" \
    '.trace | .class == "com.example.app.ComplexService"' \
    "--from+--to: trace root is ComplexService"

assert_json_contains "$OUT/sliced-from-to.json" \
    '.trace.children[0] | .class == "com.example.app.ExceptionService"' \
    "--from+--to: child is ExceptionService"

assert_json_contains "$OUT/sliced-from-to.json" \
    '.trace.children[0].children | length == 0' \
    "--from+--to: ExceptionService is a leaf (children stripped)"

assert_json_contains "$OUT/sliced-from-to.json" \
    '.refIndex | length == 1' \
    "--from+--to: refIndex populated for ref node"

# Full pipeline: expanded → semantic → dot
$UV ftrace-semantic --input "$OUT/expanded.json" --output "$OUT/sliced-semantic.json"

assert_json_contains "$OUT/sliced-semantic.json" \
    '.nodes | length > 0' \
    "sliced semantic graph has nodes"

$UV ftrace-semantic-to-dot --input "$OUT/sliced-semantic.json" --output "$OUT/sliced-pipeline.dot"

assert_file_contains "$OUT/sliced-pipeline.dot" "digraph" \
    "sliced DOT output is a digraph"

# Fully piped: cat | slice | expand-refs | semantic | to-dot (all stdin/stdout)
cat "$OUT/complex.json" \
  | $UV ftrace-inter-slice --from com.example.app.ExceptionService \
  | $UV ftrace-expand-refs \
  | $UV ftrace-semantic \
  | $UV ftrace-semantic-to-dot > "$OUT/piped.dot"

assert_file_contains "$OUT/piped.dot" "digraph" \
    "piped pipeline produces a digraph"

assert_file_contains "$OUT/piped.dot" "handleException" \
    "piped pipeline DOT contains handleException"

# End-to-end piped: xtrace | slice | expand-refs | semantic | to-dot (no intermediate files)
$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.ComplexService --from-line "$COMPLEX_LINE" \
  | $UV ftrace-inter-slice --from com.example.app.ExceptionService \
  | $UV ftrace-expand-refs \
  | $UV ftrace-semantic \
  | $UV ftrace-semantic-to-dot > "$OUT/e2e-piped.dot"

assert_file_contains "$OUT/e2e-piped.dot" "digraph" \
    "e2e piped from xtrace produces a digraph"

assert_file_contains "$OUT/e2e-piped.dot" "handleException" \
    "e2e piped from xtrace contains handleException"

report
