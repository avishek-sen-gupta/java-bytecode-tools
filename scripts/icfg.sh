#!/usr/bin/env bash
# Thin launcher for the IcfgCLI interprocedural CFG tool.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JAVA_CP="$REPO_ROOT/java/target/classes:$REPO_ROOT/java/target/dependency/*"

exec java -Xss4m -Xmx8g \
  -Dorg.slf4j.simpleLogger.defaultLogLevel=info \
  -Dorg.slf4j.simpleLogger.showDateTime=true \
  -Dorg.slf4j.simpleLogger.dateTimeFormat="HH:mm:ss.SSS" \
  -cp "$JAVA_CP" tools.source.icfg.IcfgCLI "$@"
