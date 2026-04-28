#!/usr/bin/env bash
# Test: block edges survive the full pipeline (xtrace → semantic → dot).
# Regression test for the bug where buildBlockTrace edges were not propagated
# to the trace JSON, causing the semantic graph to have no intra-method edges.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace edges pipeline (forward)"

# ── Forward trace: edges in raw JSON ──

$B xtrace --call-graph "$OUT/callgraph.json" \
  --from com.example.app.OrderService --from-line "$PROCESS_LINE" \
  --output "$OUT/edges_fwd.json" 2>/dev/null

assert_json_contains "$OUT/edges_fwd.json" \
    '.trace.edges | length > 0' \
    "forward: root has edges"

assert_json_contains "$OUT/edges_fwd.json" \
    '.trace.edges[] | select(.label == "T" or .label == "F") | .fromBlock' \
    "forward: has branch-labeled edges (T/F)"

assert_json_contains "$OUT/edges_fwd.json" \
    '.refIndex | to_entries[] | select(.value.edges | length > 0) | .value.method' \
    "forward: child methods also have edges"

# ── Forward trace: edges survive semantic transform ──

cd "$REPO_ROOT/python"
uv run ftrace-semantic --input "$OUT/edges_fwd.json" --output "$OUT/edges_semantic.json"

assert_json_contains "$OUT/edges_semantic.json" \
    '.edges | length > 0' \
    "semantic: has intra-method edges"

assert_json_contains "$OUT/edges_semantic.json" \
    '.edges[] | select(.branch == "T" or .branch == "F") | .from' \
    "semantic: branch edges preserved"

# ── Forward trace: edges appear in DOT output ──

uv run ftrace-to-dot --input "$OUT/edges_semantic.json" --output "$OUT/edges.dot"

assert_file_contains "$OUT/edges.dot" 'n0' \
    "DOT: contains graph nodes"

assert_file_contains "$OUT/edges.dot" 'label="T"' \
    "DOT: has true-branch label"

assert_file_contains "$OUT/edges.dot" 'label="F"' \
    "DOT: has false-branch label"

report
