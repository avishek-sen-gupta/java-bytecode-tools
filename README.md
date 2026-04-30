# Java Bytecode Tools

[![CI](https://github.com/avishek-sen-gupta/java-bytecode-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/avishek-sen-gupta/java-bytecode-tools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE.md)

Interprocedural call tracing via [SootUp](https://soot-oss.github.io/SootUp/) bytecode analysis. Given any code path you want to understand — "what happens when this method fires?" or "what calls this DAO method?" — these tools build a structural call graph from compiled `.class` files and let you trace through it in both directions, producing JSON trees and SVG visualizations.

The repository combines:

- A Java CLI built on SootUp for call-graph construction and interprocedural tracing
- A small Python toolchain for slicing, ref expansion, validation, semantic graph building, and DOT/SVG rendering
- A fixture project plus end-to-end tests that exercise the full pipeline

**Forward trace of `OrderService.processOrder`** — branches, calls to repository and internal methods, resolved down to source lines:

<p align="center">
  <img src="docs/forward-trace-example.svg" alt="Forward trace visualization" width="700">
</p>

## What Is In The Repo

```text
java-bytecode-tools/
├── java/                    Maven project — SootUp-based analysis
│   ├── pom.xml
│   └── src/main/java/tools/bytecode/
│       ├── ForwardTracer.java    Two-pass ref-by-default tracer
│       ├── BackwardTracer.java   BFS over call graph for backward traces
│       ├── CallGraphBuilder.java Scans bytecode, resolves dispatch
│       └── cli/                 picocli subcommands
├── python/                  uv-managed post-processing and rendering tools
│   ├── ftrace_types.py      Shared type definitions (StrEnum, TypedDict)
│   ├── ftrace_slice.py      Slice subtree + bundle ref index
│   ├── ftrace_expand_refs.py Expand ref nodes using ref index
│   ├── ftrace_semantic.py   Transform raw trace → semantic graph
│   ├── ftrace_to_dot.py     Render semantic graph as DOT/SVG
│   ├── ftrace_validate.py   Validate semantic graph structure
│   ├── frames_print.py      Pretty-print backward trace chains
│   ├── jspmap/              jspmap package — JSP-to-DAO semantic map tool
│   │   ├── protocols.py     BeanInfo + BeanResolver plugin protocol
│   │   ├── jsf_bean_map.py  JsfBeanResolver — reads faces-config.xml
│   │   ├── jsp_parser.py    EL tokenizer, DOM walk, ELAction
│   │   ├── chain_builder.py BFS chain builder, ChainHop
│   │   └── jspmap.py        CLI entry point + resolver registry
├── scripts/bytecode.sh      Thin launcher for the Java CLI
├── test-fixtures/           Fixture classes and end-to-end tests
│   ├── src/                 Small fixture Java project
│   ├── tests/               One test script per feature area
│   ├── lib-test.sh          Shared helpers, setup, and assertions
│   └── run-e2e.sh           E2E test runner
├── build.sh                 Prereq check + Java/Python setup
└── run-all-tests.sh         Java, Python, and E2E test runner
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
- `jspmap`: map JSP EL actions through call graph to DAO methods; outputs JSON semantic map

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

### Pre-Commit Hooks

```bash
pre-commit install
```

Hooks run automatically on commit:

- [Black](https://github.com/psf/black) — Python formatting
- [google-java-format](https://github.com/google/google-java-format) — Java formatting
- [Talisman](https://github.com/thoughtworks/talisman) — secret detection
- [Pyright](https://github.com/microsoft/pyright) — Python type checking
- [pip-audit](https://github.com/pypa/pip-audit) — Python dependency vulnerability scanning
- E2E test suite

## Command Shape

All Java commands go through `scripts/bytecode.sh`:

```bash
scripts/bytecode.sh [--prefix <package-prefix>] <classpath> <subcommand> [options]
```

Notes:

- `--prefix` limits analysis to classes whose fully qualified name starts with the given prefix. Without it, every class visible on the classpath is analyzed.
- `<classpath>` is a colon-separated classpath of compiled classes and jars
- Java JSON-producing commands write to stdout by default; use `--output <file>` to write a file instead
- Python tools that accept `--input` also read from stdin when `--input` is omitted
- Python tools that accept `--output` write to stdout when `--output` is omitted

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

Scans all project classes matching the prefix, extracts invoke statements, and records caller-to-callee edges. Resolves polymorphic dispatch by mapping interfaces to concrete implementations.

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

### 2. Find A Method And Its Source Lines

Use `dump` to resolve a class to method ranges:

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  dump com.example.app.OrderService --output order-service.json
```

The output includes each method's `lineStart` and `lineEnd`. Those line numbers are how `xtrace` and `frames` identify entry and target methods.

### 3. Forward Trace From An Entry Point

Identify the entry method by source line or by method name:

```bash
# By line number (use `dump` to find the line)
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json \
  --from com.example.app.OrderService --from-line 17 \
  --output forward.json

# By method name (simpler when the name is unambiguous)
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json \
  --from com.example.app.OrderService --from-method processOrder \
  --output forward.json
```

`--from-line` and `--from-method` are mutually exclusive; exactly one is required. If the method name is overloaded, the error message lists all overloads with their line numbers so you can switch to `--from-line` to disambiguate.

`xtrace` is implemented as a two-pass pipeline:

1. **Discover** — DFS over the call graph from the entry point, classifying each reachable method as normal, cycle, or filtered
2. **Build** — construct CFG-rich method bodies for the root; emit all other methods as lightweight `ref` nodes with their full bodies in a flat `refIndex`

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
cd python && uv run frames-print --input ../backward.json
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

### Piping And Streaming

The post-processing tools are designed to compose as Unix filters.

- `ftrace-slice`, `ftrace-expand-refs`, `ftrace-semantic`, `ftrace-validate`, `ftrace-to-dot`, and `frames-print` read stdin if `--input` is omitted
- Those same tools write stdout if `--output` is omitted
- Java CLI commands such as `buildcg`, `dump`, `xtrace`, `frames`, and `trace` write JSON to stdout when `--output` is omitted

Examples:

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json \
  --from com.example.app.OrderService --from-line 17 \
  > forward.json
```

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  frames --call-graph callgraph.json \
  --to com.example.app.JdbcOrderRepository --to-line 7 \
  | uv --directory python run frames-print
```

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json \
  --from com.example.app.OrderService --from-line 17 \
  | uv --directory python run ftrace-slice --to com.example.app.JdbcOrderRepository \
  | uv --directory python run ftrace-expand-refs \
  | uv --directory python run ftrace-semantic \
  | uv --directory python run ftrace-to-dot \
  > trace.dot
```

If you want a rendered SVG directly, keep the upstream stages on stdout and give only the final renderer an output path:

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json \
  --from com.example.app.OrderService --from-line 17 \
  | uv --directory python run ftrace-slice --to com.example.app.JdbcOrderRepository \
  | uv --directory python run ftrace-expand-refs \
  | uv --directory python run ftrace-semantic \
  | uv --directory python run ftrace-to-dot --output trace.svg
```

### Slice A Trace

```bash
uv --directory python run ftrace-slice \
  --input forward.json \
  --from com.example.app.OrderService --from-line 17 \
  --output slice.json
```

Common modes:

- `--from CLASS [--from-line N]`: return the subtree rooted at that method
- `--to CLASS [--to-line N]`: keep only paths from the root that reach the target
- `--from ... --to ...`: find the `--from` subtree, then prune it to paths that reach `--to`

The sliced output has the same envelope shape as `xtrace` output:

```json
{
  "trace": {
    "class": "com.example.app.OrderService",
    "method": "processOrder",
    "methodSignature": "<com.example.app.OrderService: java.lang.String processOrder(int)>",
    "lineStart": 16,
    "lineEnd": 24,
    "children": [
      {
        "class": "com.example.app.JdbcOrderRepository",
        "method": "findById",
        "methodSignature": "<com.example.app.JdbcOrderRepository: java.lang.String findById(int)>",
        "callSiteLine": 17,
        "ref": true
      }
    ]
  },
  "refIndex": {
    "<com.example.app.JdbcOrderRepository: java.lang.String findById(int)>": {
      "class": "com.example.app.JdbcOrderRepository",
      "method": "findById",
      "lineStart": 6,
      "lineEnd": 11,
      "blocks": [],
      "edges": [],
      "traps": [],
      "children": []
    }
  }
}
```

The bundled `refIndex` is reduced to only the signatures still referenced by the slice.

### Expand Ref Nodes

```bash
uv --directory python run ftrace-expand-refs --input slice.json --output expanded.json
```

This replaces `ref: true` leaves with full method bodies from `refIndex` while preserving `callSiteLine` metadata and avoiding cyclic expansion. Both sliced traces (from `ftrace-slice`) and raw envelopes (from `xtrace`) are accepted — so you can expand the whole trace without slicing first:

```bash
uv --directory python run ftrace-expand-refs --input forward.json --output expanded.json
```

### Build A Semantic Graph And Render SVG

```bash
uv --directory python run ftrace-semantic --input expanded.json --output semantic.json
uv --directory python run ftrace-to-dot --input semantic.json --output trace.svg
```

The semantic pass merges duplicate source-line statements, assigns exception clusters, and emits graph-friendly nodes and edges. The renderer maps that JSON into DOT/SVG with:

- **Method clusters** — one subgraph per method, labeled `Class.method [lines X–Y]`
- **Per-line nodes** — green for calls, blue for branches, beige for assignments
- **Diamond nodes** for branch decisions with resolved conditions
- **T/F edges** for true/false branch paths
- **Red cross-cluster edges** linking call sites to callee entry nodes
- **Leaf nodes**: red dashed (cycle), grey dashed (ref), yellow dashed (filtered)

### Validate Semantic Output

```bash
uv --directory python run ftrace-validate --input semantic.json
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

- **`allow`**: if present and non-empty, only matching class prefixes are eligible for recursion. An empty list or omitting the key disables allow-filtering.
- **`stop`**: matching class prefixes are emitted as `filtered` leaves instead of being expanded.
- **Precedence**: `allow` is checked first, then `stop`. A class matching both is **stopped** (stop wins). Both filters match on class-name prefixes, not individual methods.

Without `--filter`, recursion follows every reachable method that has a body and is present in the analyzed project set.

Example:

```bash
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json \
  --from com.example.app.OrderService --from-method processOrder \
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
- checks the slice, expand, semantic, and render pipeline (both file-based and fully piped via stdin/stdout)
- validates outputs with `jq`

## Quick Reference

```bash
./build.sh

# All Java commands:
#   scripts/bytecode.sh [--prefix <pkg.>] <classpath> <subcommand> [options]

# Build call graph
scripts/bytecode.sh --prefix com.example. "$CP" buildcg --output callgraph.json

# Inspect a class
scripts/bytecode.sh --prefix com.example. "$CP" dump com.example.app.OrderService

# Forward trace (by line or by method name)
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json --from com.example.app.OrderService --from-line 17
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json --from com.example.app.OrderService --from-method processOrder

# Backward trace
scripts/bytecode.sh --prefix com.example. "$CP" \
  frames --call-graph callgraph.json --to com.example.app.JdbcOrderRepository --to-line 7

# Intraprocedural trace
scripts/bytecode.sh --prefix com.example. "$CP" trace com.example.app.OrderService 17 23

# Python post-processing
uv --directory python run ftrace-slice   --input forward.json --from com.example.app.OrderService --output slice.json
uv --directory python run ftrace-expand-refs --input slice.json --output expanded.json
uv --directory python run ftrace-semantic    --input expanded.json --output semantic.json
uv --directory python run ftrace-to-dot      --input semantic.json --output trace.svg
uv --directory python run ftrace-validate    --input semantic.json
uv --directory python run frames-print       --input backward.json

# Full pipeline piped end-to-end
scripts/bytecode.sh --prefix com.example. "$CP" \
  xtrace --call-graph callgraph.json --from com.example.app.OrderService --from-line 17 \
  | uv --directory python run ftrace-slice --to com.example.app.JdbcOrderRepository \
  | uv --directory python run ftrace-expand-refs \
  | uv --directory python run ftrace-semantic \
  | uv --directory python run ftrace-to-dot --output trace.svg
```

## Practical Notes

- The Java launcher sets `-Xss4m -Xmx2g`
- The CLI expects compiled bytecode (`.class` files), not source files
- `frames` supports `--depth` to cap backward BFS depth and `--max-chains` to cap the number of returned call chains (default: 50)
- Most JSON-writing commands create parent directories for `--output` automatically
