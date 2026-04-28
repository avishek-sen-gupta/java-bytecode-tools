#!/usr/bin/env bash
# Build script for java-bytecode-tools.
# Checks prerequisites, then builds the Java and Python projects.
set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Prereqs ──────────────────────────────────────────────────────────

check_cmd() {
  command -v "$1" >/dev/null 2>&1
}

echo "Checking prerequisites…"

# Java 21+
if ! check_cmd java; then
  echo "ERROR: java not found. Install JDK 21+ (e.g. brew install openjdk@21)" >&2
  exit 1
fi
JAVA_VER=$(java -version 2>&1 | head -1 | sed -E 's/.*"([0-9]+).*/\1/')
if [ "$JAVA_VER" -lt 21 ] 2>/dev/null; then
  echo "ERROR: Java 21+ required (found $JAVA_VER)" >&2
  exit 1
fi
echo "  java $JAVA_VER ✓"

# Maven
if ! check_cmd mvn; then
  echo "ERROR: mvn not found. Install Maven (e.g. brew install maven)" >&2
  exit 1
fi
echo "  mvn ✓"

# Python 3.13+
if ! check_cmd python3; then
  echo "ERROR: python3 not found. Install Python 3.13+ (e.g. brew install python@3.13)" >&2
  exit 1
fi
PY_VER=$(python3 -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_VER" -lt 13 ] 2>/dev/null; then
  echo "ERROR: Python 3.13+ required (found 3.$PY_VER)" >&2
  exit 1
fi
echo "  python3.${PY_VER} ✓"

# jq (required by E2E tests)
if ! check_cmd jq; then
  echo "ERROR: jq not found. Install via: brew install jq" >&2
  exit 1
fi
echo "  jq ✓"

# uv
if ! check_cmd uv; then
  echo "ERROR: uv not found. Install via: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi
echo "  uv ✓"

# ── Build Java ───────────────────────────────────────────────────────

echo ""
echo "Building Java project…"
(cd "$REPO_ROOT/java" && mvn -q compile)
echo "  Java build complete."

# ── Build Python ─────────────────────────────────────────────────────

echo ""
echo "Setting up Python environment…"
(cd "$REPO_ROOT/python" && uv sync -q)
echo "  Python environment ready."

# ── Compile test fixtures ────────────────────────────────────────────

echo ""
echo "Compiling test fixtures…"
mkdir -p "$REPO_ROOT/test-fixtures/classes"
javac -g -d "$REPO_ROOT/test-fixtures/classes" \
  "$REPO_ROOT"/test-fixtures/src/com/example/app/*.java
echo "  Fixture classes compiled."

echo ""
echo "Build complete. Run analyses with: scripts/bytecode.sh"
