#!/usr/bin/env bash
# Shared test helpers and setup for e2e tests.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURE="$SCRIPT_DIR"
CP="$FIXTURE/classes"
B="$REPO_ROOT/scripts/bytecode.sh --prefix com.example. $CP"
OUT="$FIXTURE/target"

PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  ✗ $1"; echo "    $2"; }

assert_json_field() {
    local file="$1" field="$2" expected="$3" label="$4"
    local actual
    actual=$(jq -r "$field" "$file" 2>/dev/null) || { fail "$label" "jq parse error"; return; }
    if [ "$actual" = "$expected" ]; then
        pass "$label"
    else
        fail "$label" "expected '$expected', got '$actual'"
    fi
}

assert_json_gt() {
    local file="$1" field="$2" min="$3" label="$4"
    local actual
    actual=$(jq -r "$field" "$file" 2>/dev/null) || { fail "$label" "jq parse error"; return; }
    if [ "$actual" -gt "$min" ] 2>/dev/null; then
        pass "$label"
    else
        fail "$label" "expected > $min, got '$actual'"
    fi
}

assert_json_contains() {
    local file="$1" expr="$2" label="$3"
    if jq -e "$expr" "$file" >/dev/null 2>&1; then
        pass "$label"
    else
        fail "$label" "jq expression '$expr' returned false"
    fi
}

assert_file_contains() {
    local file="$1" pattern="$2" label="$3"
    if grep -q "$pattern" "$file" 2>/dev/null; then
        pass "$label"
    else
        fail "$label" "pattern '$pattern' not found in $file"
    fi
}

assert_file_smaller() {
    local file_a="$1" file_b="$2" label="$3"
    local size_a size_b
    size_a=$(wc -c < "$file_a" | tr -d ' ')
    size_b=$(wc -c < "$file_b" | tr -d ' ')
    if [ "$size_a" -lt "$size_b" ]; then
        pass "$label ($size_a < $size_b bytes)"
    else
        fail "$label" "$size_a >= $size_b bytes"
    fi
}

# ── Setup ────────────────────────────────────────────────────────────

setup() {
    # Compile fixture if needed
    if [ ! -d "$CP/com/example/app" ]; then
        javac -g -d "$CP" "$FIXTURE"/src/com/example/app/*.java
    fi

    # Build tools if needed
    if [ ! -d "$REPO_ROOT/java/target/classes" ]; then
        echo "  Building tools (mvn compile)…"
        (cd "$REPO_ROOT/java" && mvn -q compile)
    fi

    rm -rf "$OUT"
    mkdir -p "$OUT"

    # Build call graph (shared by most tests)
    $B buildcg --output "$OUT/callgraph.json"

    # Dump class metadata (used by several tests for line numbers)
    $B dump com.example.app.OrderService > "$OUT/dump-svc.json"
    $B dump com.example.app.JdbcOrderRepository > "$OUT/dump-repo.json"
    $B dump com.example.app.OrderController > "$OUT/dump-ctrl.json"
    $B dump com.example.app.ExceptionService > "$OUT/dump-exc.json"
    $B dump com.example.app.ComplexService > "$OUT/dump-complex.json"
    $B dump com.example.app.RecursionService > "$OUT/dump-rec.json"
    $B dump com.example.app.NestedExceptionService > "$OUT/dump-nested.json"
}

# Extract line numbers from dumps (call after setup)
load_line_numbers() {
    PROCESS_LINE=$(jq -r '.methods[] | select(.method == "processOrder") | .lineStart' "$OUT/dump-svc.json")
    PROCESS_END=$(jq -r '.methods[] | select(.method == "processOrder") | .lineEnd' "$OUT/dump-svc.json")
    ORDER_EXISTS_LINE=$(jq -r '.methods[] | select(.method == "orderExists") | .lineStart' "$OUT/dump-svc.json")
    FIND_BY_ID_LINE=$(jq -r '.methods[] | select(.method == "findById") | .lineStart' "$OUT/dump-repo.json")
    HANDLE_GET_LINE=$(jq -r '.methods[] | select(.method == "handleGet") | .lineStart' "$OUT/dump-ctrl.json")
    EXCEPTION_LINE=$(jq -r '.methods[] | select(.method == "handleException") | .lineStart' "$OUT/dump-exc.json")
    COMPLEX_LINE=$(jq -r '.methods[] | select(.method == "entryMethod") | .lineStart' "$OUT/dump-complex.json")
    RECURSE_LINE=$(jq -r '.methods[] | select(.method == "recurse") | .lineStart' "$OUT/dump-rec.json")
    NESTED_LINE=$(jq -r '.methods[] | select(.method == "nestedHandle") | .lineStart' "$OUT/dump-nested.json")
}

report() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    local total=$((PASS + FAIL))
    echo "Results: $PASS/$total passed"
    if [ "$FAIL" -gt 0 ]; then
        echo "$FAIL FAILED"
        return 1
    else
        echo "All tests passed."
    fi
}
