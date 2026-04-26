# Java Bytecode Tools

[![CI](https://github.com/avishek-sen-gupta/java-bytecode-tools/actions/workflows/ci.yml/badge.svg)](https://github.com/avishek-sen-gupta/java-bytecode-tools/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE.md)

Interprocedural call tracing via [SootUp](https://soot-oss.github.io/SootUp/) bytecode analysis. Given any code path you want to understand — "what happens when this method fires?" or "what calls this DAO method?" — these tools build a structural call graph from compiled `.class` files and let you trace through it in both directions, producing JSON trees and SVG visualizations.

## Setup

```bash
./build.sh
```

Requires Java 21+, Maven, Python 3.13+, and [uv](https://github.com/astral-sh/uv). The build script checks prerequisites, compiles the Java project, and sets up the Python environment.

### Pre-commit hooks

```bash
pre-commit install
```

Hooks run automatically on commit: [Black](https://github.com/psf/black) (Python), [google-java-format](https://github.com/google/google-java-format) (Java), [Talisman](https://github.com/thoughtworks/talisman) (secret detection), and the e2e test suite.

## Project Structure

```
java-bytecode-tools/
├── java/                    # Maven project — SootUp-based analysis
│   ├── pom.xml
│   └── src/main/java/tools/bytecode/
│       ├── BytecodeTracer.java
│       ├── ForwardTracer.java
│       ├── BackwardTracer.java
│       ├── CallGraphBuilder.java
│       └── cli/             # picocli CLI commands
├── python/                  # uv project — visualization tools
│   ├── pyproject.toml
│   ├── ftrace_to_dot.py     # Render forward trace as SVG
│   └── ftrace_expand_refs.py # Expand deduplicated ref nodes
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

Scans all project classes matching the prefix, extracts invoke statements, and records caller-to-callee edges. Resolves polymorphic dispatch by mapping interfaces to implementations.

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  buildcg --output callgraph.json
```

### Step 2: Find the method you care about

```bash
scripts/bytecode.sh --prefix com.example. /path/to/classes \
  dump com.example.service.OrderService
```

Output lists every method with its source line range. Pick the method and note its `lineStart`.

### Step 3: Trace

#### Forward trace — "what does this method call?"

Traces downward through all callees, building a recursive tree with per-method block-level CFG, branch conditions, and call sites.

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

### Step 4 (optional): Expand ref nodes

Large traces deduplicate repeated methods as `ref` nodes. Expand before visualizing:

```bash
cd python && uv run ftrace-expand-refs \
  --subtree ../trace.json --full-tree ../trace.json --output ../expanded.json
```

### Step 5: Visualize as SVG

```bash
cd python && uv run ftrace-to-dot --input ../trace.json --output ../trace.svg
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

- **`allow`**: only recurse into classes matching these prefixes
- **`stop`**: stop recursion at classes matching these prefixes (appear as filtered leaf nodes)

Without `--filter`, the tracer recurses into everything reachable.

## Testing

Run the full e2e suite:

```bash
bash test-fixtures/run-e2e.sh
```

Or run a single test case:

```bash
bash test-fixtures/tests/test_xtrace_forward.sh
```

Tests compile a small fixture project (`test-fixtures/src/`), exercise every CLI command and flag, and validate the JSON output with `jq`. Requires `jq` to be installed.

## Quick reference

```bash
./build.sh

# Every command starts with:
#   scripts/bytecode.sh --prefix <pkg.prefix.> /path/to/classes <subcommand>

scripts/bytecode.sh --prefix com.example. /path/to/classes buildcg --output callgraph.json
scripts/bytecode.sh --prefix com.example. /path/to/classes dump <class>
scripts/bytecode.sh --prefix com.example. /path/to/classes xtrace --call-graph callgraph.json --from <class> --from-line <N> --output out.json
scripts/bytecode.sh --prefix com.example. /path/to/classes xtrace --call-graph callgraph.json --to <class> --to-line <N> --collapse
scripts/bytecode.sh --prefix com.example. /path/to/classes xtrace --call-graph callgraph.json --to <class> --to-line <N> --collapse --flat

cd python
uv run ftrace-to-dot --input ../out.json --output ../out.svg
uv run ftrace-expand-refs --subtree ../sub.json --full-tree ../full.json --output ../expanded.json
```
