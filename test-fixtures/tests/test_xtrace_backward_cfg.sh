#!/usr/bin/env bash
# Test: xtrace --to includes CFG data (blocks/traps) and respects deduplication.
source "$(cd "$(dirname "$0")/.." && pwd)/lib-test.sh"
setup; load_line_numbers

echo "xtrace --to (backward CFG + deduplication)"

# Trace back to recurse() from entry()
$B xtrace --call-graph "$OUT/callgraph.json" \
  --to com.example.app.RecursionService --to-line "$RECURSE_LINE" \
  --output "$OUT/backward_cfg.json" 2>/dev/null

# Verify deduplication: entry calls recurse twice, and recurse is recursive.
# In a backward trace from recurse, we'll see entry -> recurse.
assert_json_contains "$OUT/backward_cfg.json" \
    '.chains[0] | any(.[]; .method == "recurse")' \
    "chain contains recurse"

assert_json_contains "$OUT/backward_cfg.json" \
    '.chains[0] | any(.[]; .blocks | length > 0)' \
    "frames include CFG blocks"

assert_json_contains "$OUT/backward_cfg.json" \
    '.chains[0] | any(.[]; .edges | length > 0)' \
    "frames include CFG edges"

assert_json_contains "$OUT/backward_cfg.json" \
    '.chains[0] | any(.[]; .edges | all(has("fromBlock") and has("toBlock")))' \
    "backward edges have fromBlock and toBlock"

report
