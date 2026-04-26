#!/usr/bin/env bash
# End-to-end test runner for java-bytecode-tools.
# Runs each test case in test-fixtures/tests/ independently.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TESTS_DIR="$SCRIPT_DIR/tests"

PASSED=0
FAILED=0
FAILURES=()

for test_file in "$TESTS_DIR"/test_*.sh; do
    name="$(basename "$test_file" .sh)"
    echo ""
    echo "── $name ──"
    if bash "$test_file"; then
        PASSED=$((PASSED + 1))
    else
        FAILED=$((FAILED + 1))
        FAILURES+=("$name")
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
TOTAL=$((PASSED + FAILED))
echo "Test cases: $PASSED/$TOTAL passed"
if [ "$FAILED" -gt 0 ]; then
    echo "$FAILED FAILED:"
    for f in "${FAILURES[@]}"; do
        echo "  - $f"
    done
    exit 1
else
    echo "All test cases passed."
fi
