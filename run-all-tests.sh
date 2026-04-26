#!/usr/bin/env bash
# Run all tests: Java unit, Python unit, and E2E.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
FAILED=0

section() { printf '\n━━━ %s ━━━\n' "$1"; }

section "Java unit tests"
if (cd "$ROOT/java" && mvn test -q); then
  echo "  ✓ Java unit tests passed"
else
  echo "  ✗ Java unit tests failed"
  FAILED=1
fi

section "Python unit tests"
if (cd "$ROOT/python" && python3 -m pytest tests/ -q); then
  echo "  ✓ Python unit tests passed"
else
  echo "  ✗ Python unit tests failed"
  FAILED=1
fi

section "E2E tests"
if bash "$ROOT/test-fixtures/run-e2e.sh"; then
  echo "  ✓ E2E tests passed"
else
  echo "  ✗ E2E tests failed"
  FAILED=1
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "All test suites passed."
else
  echo "Some test suites failed."
  exit 1
fi
