#!/usr/bin/env bash
# Thin launcher for the picocli-based bytecode CLI.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JAVA_CP="$REPO_ROOT/java/target/classes:$REPO_ROOT/java/target/dependency/*"

exec java -Xss4m -Xmx2g -cp "$JAVA_CP" tools.bytecode.cli.CLI "$@"
