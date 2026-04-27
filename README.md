# Java Bytecode Tools

[![CI](https://github.com/avishek-sen-gupta/java-bytecode-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/avishek-sen-gupta/java-bytecode-tools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE.md)

Interprocedural call tracing via [SootUp](https://soot-oss.github.io/SootUp/) bytecode analysis. Given any code path you want to understand — "what happens when this method fires?" or "what calls this DAO method?" — these tools build a structural call graph from compiled `.class` files and let you trace through it in both directions, producing JSON trees and SVG visualizations.

**Forward trace of `OrderService.processOrder`** — branches, calls to repository and internal methods, resolved down to source lines:

<p align="center">
  <img src="docs/forward-trace-example.svg" alt="Forward trace visualization" width="700">
</p>

## Setup

```bash
./build.sh
```

Requires Java 21+, Maven, Python 3.13+, and [uv](https://github.com/astral-sh/uv). The build script checks prerequisites, compiles the Java project, and sets up the Python environment.

### Pre-commit hooks

```bash
pre-commit install
```

Hooks run automatically on commit: [Black](https://github.com/psf/black) (Python), [google-java-format](https://github.com/google/google-java-format) (Java), [Talisman](https://github.com/thoughtworks/talisman) (secret detection), [Pyright](https://github.com/microsoft/pyright) (Python type checking), [pip-audit](https://github.com/pypa/pip-audit) (Python dependency vulnerability scanning), and the e2e test suite.

## Project Structure

```
java-bytecode-tools/
├── java/                    # Maven project — SootUp-based analysis
│   ├── pom.xml
│   └── src/main/java/tools/bytecode/
│       ├── BytecodeTracer.java
│       ├── ForwardTracer.java   # Two-pass ref-by-default tracer
│       ├── BackwardTracer.java
│       ├── CallGraphBuilder.java
│       ├── Classification.java  # NORMAL / CYCLE / FILTERED enum
│       ├── DiscoveryResult.java # Pass 1 output record
│       └── cli/             # picocli CLI commands
├── python/                  # uv project — visualization tools
│   ├── pyproject.toml
│   ├── ftrace_types.py      # Shared type definitions (StrEnum, TypedDict)
│   ├── ftrace_slice.py      # Slice subtree + bundle ref index
│   ├── ftrace_expand_refs.py # Expand ref nodes using ref index
│   ├── ftrace_semantic.py   # Transform raw trace → semantic graph
│   └── ftrace_to_dot.py     # Render semantic graph as DOT/SVG
├── scripts/
│   └── bytecode.sh          # CLI launcher
├── test-fixtures/           # E2e tests
│   ├── src/                 # Small fixture Java project
│   ├── tests/               # One test script per CLI feature
│   ├── lib-test.sh          # Shared helpers and setup
│   └── run-e2e.sh           # Test runner
├── build.sh                 # Install deps + build
└── README.md
```

## Usage

All commands go through `scripts/bytecode.sh`. It takes two required arguments: `--prefix` (scopes analysis to your project's package namespace) and the classpath to your compiled `.class` files.

### Step 1: Build the call graph

Scans all project classes matching the prefix, extracts invoke statements, and records caller-to-callee edges. Resolves polymorphic dispatch by mapping interfaces to implementations. Progress is printed to stderr every 1000 methods during indexing and scanning.

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  buildcg --output callgraph.json
```

Omit `--output` to write JSON to stdout (Unix pipeline semantics):

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes buildcg > callgraph.json
```

### Step 2: Find the method you care about

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  dump com.example.service.OrderService
```

Output lists every method with its source line range. Pick the method and note its `lineStart`.

### Step 3: Trace

#### Forward trace — "what does this method call?"

Traces downward through all callees using a two-pass architecture:
1. **Discover** — DFS over the call graph classifying each method as normal, cycle, or filtered
2. **Build** — construct block-level CFGs for each discovered method in a flat loop (no recursion)

Output is an **envelope** with the root method's full CFG and a flat `refIndex` of all other methods:

```json
{
  "trace": { "class": "OrderService", "method": "processOrder", "blocks": [...], "children": [...] },
  "refIndex": { "<com.example.OrderDao: void save()>": { "blocks": [...], ... }, ... }
}
```

Every method except the root is a **ref node** by default — a lightweight pointer into the refIndex. This makes the output deterministic (not dependent on DFS traversal order) and enables targeted expansion via `ftrace-expand-refs`.

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  xtrace --call-graph callgraph.json \
  --from com.example.service.OrderService --from-line 64 \
  --output trace.json
```

Use `--filter` to control recursion depth:

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  xtrace --call-graph callgraph.json \
  --from com.example.service.OrderService --from-line 64 \
  --filter config/my-filter.json \
  --output trace.json
```

#### Backward trace — "what calls this method?"

BFS backward through the call graph to find every entry point that reaches a target.

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  xtrace --call-graph callgraph.json \
  --to com.example.dao.OrderDao --to-line 39 \
  --collapse \
  --output backward-trace.json
```

Use `--flat` for lightweight stack-trace output (no sourceTrace/blocks, faster):

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  xtrace --call-graph callgraph.json \
  --to com.example.dao.OrderDao --to-line 39 \
  --collapse --flat \
  --output backward-trace-flat.json
```

#### Bidirectional — constrain to a specific path

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  xtrace --call-graph callgraph.json \
  --from com.example.service.OrderService --from-line 64 \
  --to com.example.dao.OrderDao --to-line 39
```

### Step 4 (optional): Slice and expand

Since every callee is a ref node, you can drill into any method by slicing and expanding:

```bash
cd python

# Slice: extract subtree + bundle ref index
uv run ftrace-slice \
  --input ../trace.json \
  --query ".trace.children[0]" \
  --output ../sliced.json

# Expand refs: replace ref nodes with full method bodies
uv run ftrace-expand-refs \
  --input ../sliced.json \
  --output ../expanded.json
```

`ftrace-expand-refs` accepts both sliced traces (from `ftrace-slice`) and raw envelopes (from `xtrace`) — so you can also expand the entire trace directly:

```bash
uv run ftrace-expand-refs --input ../trace.json --output ../expanded.json
```

Or pipe the whole thing — all tools (including xtrace) support stdin/stdout:

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  xtrace --call-graph callgraph.json \
  --from com.example.service.OrderService --from-line 64 \
  | cd python && uv run ftrace-slice --query ".trace.children[0]" \
  | uv run ftrace-expand-refs \
  | uv run ftrace-semantic \
  | uv run ftrace-to-dot > ../sliced.svg
```

This creates a standalone JSON for that method, including its full CFG, source trace, and exception clusters. The expanded output is ready for `ftrace-semantic`.

### Step 5: Visualize as SVG

The visualization pipeline has two stages: first transform the raw trace into a semantic graph (merging statements, assigning trap clusters, deduplicating blocks), then render it as DOT/SVG.

```bash
cd python

# Transform raw trace → semantic graph
uv run ftrace-semantic --input ../trace.json --output ../trace-semantic.json

# Render semantic graph → SVG
uv run ftrace-to-dot --input ../trace-semantic.json --output ../trace.svg
```

Or pipe them together:

```bash
cd python && uv run ftrace-semantic --input ../trace.json | uv run ftrace-to-dot --output ../trace.svg
```

The SVG shows:

- **Clusters** for each method (labeled `Class.method [lines X-Y]`)
- **Per-line nodes** — green for calls, blue for branches, beige for assignments
- **Diamond nodes** for branch decisions with resolved conditions
- **T/F edges** for true/false branch paths
- **Red cross-cluster edges** linking call sites to callee methods
- **Leaf nodes**: red dashed (cycle), grey dashed (ref), yellow dashed (filtered)

### Intraprocedural trace

Trace between two lines within a single method:

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  trace com.example.service.OrderService 64 120
```

## Filters

The `--filter` flag accepts a JSON file controlling forward trace recursion:

```json
{
  "allow": ["com.example"],
  "stop": ["com.example.dao", "com.example.domain", "com.example.util"]
}
```

- **`allow`**: only recurse into classes whose fully-qualified name starts with one of these prefixes. An empty list or omitting the key disables allow-filtering (all classes are allowed).
- **`stop`**: stop recursion at classes matching these prefixes — they appear as filtered leaf nodes in the trace.

**Precedence:** `allow` is checked first, then `stop`. A class matching both an allow and a stop prefix is **stopped** (stop wins). Both filters match on class-name prefixes, not individual methods.

Without `--filter`, the tracer recurses into everything reachable.

## Testing

Run all tests (Java unit, Python unit, E2E):

```bash
bash run-all-tests.sh
```

Or run individually:

```bash
cd java && mvn test                    # Java unit tests
python3 -m pytest python/tests/ -v     # Python unit tests
bash test-fixtures/run-e2e.sh          # E2E tests
```

E2E tests compile a small fixture project (`test-fixtures/src/`), exercise every CLI command and the full `xtrace → ftrace-slice → ftrace-expand-refs → ftrace-semantic → ftrace-to-dot` pipeline (both file-based and piped via stdin/stdout), and validate output with `jq`. Requires `jq` to be installed.

## Quick reference

```bash
./build.sh

# Every command starts with:
#   scripts/bytecode.sh --prefix <pkg.prefix.> /path/to/classes <subcommand>

scripts/bytecode.sh --prefix com.example. /path/to/classes buildcg --output callgraph.json   # or omit --output to write to stdout
scripts/bytecode.sh --prefix com.example. /path/to/classes dump <class>
scripts/bytecode.sh --prefix com.example. /path/to/classes xtrace --call-graph callgraph.json --from <class> --from-line <N> --output out.json
scripts/bytecode.sh --prefix com.example. /path/to/classes xtrace --call-graph callgraph.json --to <class> --to-line <N> --collapse
scripts/bytecode.sh --prefix com.example. /path/to/classes xtrace --call-graph callgraph.json --to <class> --to-line <N> --collapse --flat

cd python
uv run ftrace-semantic --input ../out.json --output ../out-semantic.json
uv run ftrace-to-dot --input ../out-semantic.json --output ../out.svg
uv run ftrace-slice --input ../trace.json --query ".trace.children[0]" --output ../sliced.json
uv run ftrace-expand-refs --input ../sliced.json --output ../expanded.json

# Or pipe the full pipeline end-to-end (xtrace writes JSON to stdout when --output is omitted):
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  xtrace --call-graph callgraph.json --from <class> --from-line <N> \
  | cd python && uv run ftrace-slice --query ".trace.children[0]" \
  | uv run ftrace-expand-refs | uv run ftrace-semantic | uv run ftrace-to-dot > ../out.svg
```
