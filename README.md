# Java Bytecode Tools

[![CI](https://github.com/avishek-sen-gupta/java-bytecode-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/avishek-sen-gupta/java-bytecode-tools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE.md)

Bytecode-level call-graph and trace tooling for compiled Java classes. The repository combines:

- A Java CLI built on [SootUp](https://soot-oss.github.io/SootUp/) for call-graph construction and interprocedural tracing
- A small Python toolchain for slicing, ref expansion, validation, semantic graph building, and DOT/SVG rendering
- A fixture project plus end-to-end tests that exercise the full pipeline

The core workflow is: build a call graph from `.class` files, trace from or to a method identified by source line, then post-process the JSON into smaller slices or rendered diagrams.

**Forward trace of `OrderService.processOrder`**

<p align="center">
  <img src="docs/forward-trace-example.svg" alt="Forward trace visualization" width="700">
</p>

## What Is In The Repo

```text
java-bytecode-tools/
├── java/                  Maven project with the SootUp-based analyzer
├── python/                uv-managed post-processing and rendering tools
├── scripts/bytecode.sh    Thin launcher for the Java CLI
├── test-fixtures/         Fixture classes and end-to-end tests
├── build.sh               Prereq check + Java/Python setup
└── run-all-tests.sh       Java, Python, and E2E test runner
```

Key Java commands:

- `buildcg`: build caller -> callee edges for project classes
- `dump`: list methods in a class with source line ranges
- `trace`: intraprocedural trace between two lines in one class
- `xtrace`: forward interprocedural trace from an entry point
- `frames`: backward interprocedural trace to a target method

Key Python commands:

- `ftrace-slice`: extract a subtree or path-constrained slice
- `ftrace-expand-refs`: replace `ref` leaves with full method bodies
- `ftrace-semantic`: normalize raw trace JSON into a semantic graph
- `ftrace-to-dot`: render semantic graph JSON as DOT/SVG
- `ftrace-validate`: validate semantic graph output
- `frames-print`: pretty-print backward trace chains

## Setup

```bash
./build.sh
```

Requirements checked by the build script:

- Java 21+
- Maven
- Python 3.13+
- `uv`
- `jq` for the end-to-end test suite

`build.sh` compiles the Java project, copies Maven runtime dependencies into `java/target/dependency/`, and creates the Python environment in `python/.venv`.

## Command Shape

All Java commands go through `scripts/bytecode.sh`:

```bash
scripts/bytecode.sh [--prefix <package-prefix>] <classpath> <subcommand> [options]
```

Notes:

- `--prefix` limits analysis to classes whose fully qualified name starts with the given prefix
- `<classpath>` is a colon-separated classpath of compiled classes and jars
- JSON-producing commands write to stdout by default; use `--output <file>` to write a file instead

Example shape:

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes buildcg --output callgraph.json
```

## Quick Start

The repository ships a small fixture application under `test-fixtures/src/com/example/app`. To generate fixture classes manually:

```bash
mkdir -p test-fixtures/classes
javac -g -d test-fixtures/classes test-fixtures/src/com/example/app/*.java
```

Then use:

```bash
CP=test-fixtures/classes
```

### 1. Build The Call Graph

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  buildcg --output callgraph.json
```

The result is a JSON map:

```json
{
  "<com.example.app.OrderController: void handleGet()>": [
    "<com.example.app.OrderService: void processOrder()>"
  ]
}
```

The builder scans project classes, indexes methods, and resolves interface/superclass dispatch by mapping abstract types to known implementations in the analyzed prefix.

### 2. Find A Method And Its Source Lines

Use `dump` to resolve a class to method ranges:

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  dump com.example.app.OrderService --output order-service.json
```

The output includes each method's `lineStart` and `lineEnd`. Those line numbers are how `xtrace` and `frames` identify entry and target methods.

### 3. Forward Trace From An Entry Point

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json \
  --from com.example.app.OrderService --from-line 17 \
  --output forward.json
```

`xtrace` is implemented as a two-pass pipeline:

1. Discover all reachable project methods from the entry point over the prebuilt call graph
2. Build CFG-rich method bodies for the root and a flat `refIndex` for discovered callees

The output is an envelope:

```json
{
  "trace": {
    "class": "com.example.app.OrderService",
    "method": "processOrder",
    "blocks": [],
    "edges": [],
    "traps": [],
    "children": []
  },
  "refIndex": {}
}
```

Important details:

- The root method body is stored under `trace`
- Non-root normal callees are emitted as lightweight `ref` nodes in `children`
- Full bodies for those `ref` nodes live in `refIndex`
- Recursive edges become `cycle` leaves
- Filtered or unresolved callees become `filtered` leaves

### 4. Backward Trace To A Target Method

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  frames --call-graph callgraph.json \
  --to com.example.app.JdbcOrderRepository --to-line 7 \
  --output backward.json
```

`frames` performs a backward BFS over the call graph and emits a lightweight nested frame tree. It does not include CFG blocks. Instead, each frame records:

- class and method
- `lineStart` / `lineEnd`
- `sourceLineCount`
- `callSiteLine` for non-root frames

Pretty-print the chain view with:

```bash
cd python
uv run frames-print --input ../backward.json
```

You can also constrain the backward search to a known entry point:

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  frames --call-graph callgraph.json \
  --from com.example.app.OrderController --from-line 15 \
  --to com.example.app.JdbcOrderRepository --to-line 7 \
  --output bidirectional.json
```

### 5. Intraprocedural Trace Within One Method

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  trace com.example.app.OrderService 17 23
```

This command stays within a single method and reports paths between two source lines.

## Post-Processing Pipeline

The Python tools operate on `xtrace` output or on derivatives of that output.

### Slice A Trace

From the repository root:

```bash
cd python

uv run ftrace-slice \
  --input ../forward.json \
  --from com.example.app.OrderService --from-line 17 \
  --output ../slice.json
```

Common modes:

- `--from CLASS [--from-line N]`: return the subtree rooted at that method
- `--to CLASS [--to-line N]`: keep only paths from the root that reach the target
- `--from ... --to ...`: find the `--from` subtree, then prune it to paths that reach `--to`

The sliced output is:

```json
{
  "slice": {},
  "refIndex": {}
}
```

The bundled `refIndex` is reduced to only the signatures still referenced by the slice.

### Expand Ref Nodes

```bash
cd python
uv run ftrace-expand-refs --input ../slice.json --output ../expanded.json
```

This replaces `ref: true` leaves with full method bodies from `refIndex` while preserving `callSiteLine` metadata and avoiding cyclic expansion.

### Build A Semantic Graph And Render SVG

```bash
cd python

uv run ftrace-semantic --input ../expanded.json --output ../semantic.json
uv run ftrace-to-dot --input ../semantic.json --output ../trace.svg
```

The semantic pass merges duplicate source-line statements, assigns exception clusters, and emits graph-friendly nodes and edges. The renderer then maps that JSON into DOT/SVG with:

- per-method clusters
- statement and branch nodes
- labeled true/false edges
- cross-method call edges
- distinct styles for `ref`, `cycle`, and `filtered` leaves

### Validate Semantic Output

```bash
cd python
uv run ftrace-validate --input ../semantic.json
```

## Filters

`xtrace` accepts `--filter <json-file>` with this shape:

```json
{
  "allow": ["com.example.app"],
  "stop": ["com.example.app.JdbcOrderRepository"]
}
```

Behavior:

- `allow`: if present and non-empty, only matching class prefixes are eligible for recursion
- `stop`: matching class prefixes are emitted as `filtered` leaves instead of being expanded
- `stop` wins if both lists match a class

Without `--filter`, recursion follows every reachable method that has a body and is present in the analyzed project set.

Example:

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json \
  --from com.example.app.OrderService --from-line 17 \
  --filter test-fixtures/filter.json \
  --output filtered.json
```

## Testing

Run everything:

```bash
bash run-all-tests.sh
```

Or run suites individually:

```bash
cd java && mvn test -q
cd python && python3 -m pytest tests/ -q
bash test-fixtures/run-e2e.sh
```

The end-to-end suite:

- compiles the fixture classes
- builds a shared call graph
- exercises `buildcg`, `dump`, `trace`, `xtrace`, and `frames`
- checks the slice, expand, semantic, and render pipeline
- validates outputs with `jq`

## Practical Notes

- The Java launcher sets `-Xss4m -Xmx2g`
- The CLI expects compiled bytecode, not source files
- `--prefix` is optional, but without it the analyzer will consider every class visible on the supplied classpath
- `frames` supports `--depth` to cap backward BFS depth
- Most JSON-writing commands create parent directories for `--output` automatically
