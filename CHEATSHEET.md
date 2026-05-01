# Bytecode Tools — Cheatsheet

Copy-paste oriented quick reference for the bytecode CLI plus the Python post-processing tools.

All Java commands go through `scripts/bytecode.sh`. Python tools run via `uv --directory python run <tool>`.

## Shell Setup

```bash
CP=test-fixtures/classes

B() { scripts/bytecode.sh --prefix com.example. "$CP" "$@"; }
UV() { uv --directory python run "$@"; }
```

Compile the fixture app if you need a local test target:

```bash
mkdir -p test-fixtures/classes
javac -g -d test-fixtures/classes test-fixtures/src/com/example/app/*.java
```

## Java CLI

### `buildcg` — Build the call graph

Basic:

```bash
$B buildcg --output callgraph.json
```

Stream to stdout:

```bash
$B buildcg > callgraph.json
```

Inspect a few callers:

```bash
jq '.callees | to_entries[:5]' callgraph.json
```

Inspect callsite lines for one method:

```bash
jq '.callsites["<com.example.app.OrderController: void handleGet()>"]' callgraph.json
```

Notes:

- Output contains `callees`, `callsites`, and `methodLines`
- Rebuild when compiled classes change

### `dump` — List methods and line ranges

Basic:

```bash
$B dump com.example.app.OrderService
```

Write to a file:

```bash
$B dump com.example.app.OrderService --output order-service.json
```

Find the line range for a named method:

```bash
jq '.methods[] | select(.method == "processOrder") | {method, lineStart, lineEnd}' order-service.json
```

List all methods in a class with line ranges:

```bash
jq '.methods[] | {method, lineStart, lineEnd}' order-service.json
```

### `xtrace` — Forward interprocedural trace

By source line:

```bash
$B xtrace \
  --call-graph callgraph.json \
  --from com.example.app.OrderService \
  --from-line 17 \
  --output forward.json
```

By method name:

```bash
$B xtrace \
  --call-graph callgraph.json \
  --from com.example.app.OrderService \
  --from-method processOrder \
  --output forward.json
```

With a filter file:

```bash
$B xtrace \
  --call-graph callgraph.json \
  --from com.example.app.OrderService \
  --from-line 17 \
  --filter test-fixtures/filter.json \
  --output forward-filtered.json
```

Stream directly into later tools:

```bash
$B xtrace \
  --call-graph callgraph.json \
  --from com.example.app.OrderService \
  --from-line 17
```

Quick inspection:

```bash
jq '.trace | {class, method, lineStart, lineEnd}' forward.json
jq 'keys' forward.json
jq '.refIndex | keys[:10]' forward.json
```

Notes:

- `--from-line` and `--from-method` are mutually exclusive
- Output shape is `{ "trace": ..., "refIndex": ... }`
- Non-root callees are usually emitted as `ref` leaves

## Python Tools

These tools read stdin when `--input` is omitted and write stdout when `--output` is omitted, so pipelines compose naturally.

### `rev-calltree` — Backward call graph to a target

Find all callers that reach a target line:

```bash
$UV rev-calltree \
  --call-graph callgraph.json \
  --to-class com.example.app.JdbcOrderRepository \
  --to-line 7 \
  > backward.json
```

Constrain the search to a known entry point:

```bash
$UV rev-calltree \
  --call-graph callgraph.json \
  --from-class com.example.app.OrderController \
  --from-line 15 \
  --to-class com.example.app.JdbcOrderRepository \
  --to-line 7 \
  > backward-from-controller.json
```

Limit depth and number of chains:

```bash
$UV rev-calltree \
  --call-graph callgraph.json \
  --to-class com.example.app.JdbcOrderRepository \
  --to-line 7 \
  --max-depth 8 \
  --max-chains 20 \
  > backward-small.json
```

Inspect metadata:

```bash
jq '.metadata' backward.json
```

### `frames-print` — Pretty-print backward chains

From a saved file:

```bash
$UV frames-print --input backward.json
```

Write to a text file:

```bash
$UV frames-print --input backward.json --output backward.txt
```

Pipe directly from `rev-calltree`:

```bash
$UV rev-calltree \
  --call-graph callgraph.json \
  --to-class com.example.app.JdbcOrderRepository \
  --to-line 7 \
  | $UV frames-print
```

### `fw-calltree` — Forward method-level call graph

Build a method-only reachable graph:

```bash
$UV fw-calltree \
  --callgraph callgraph.json \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  > calltree.json
```

Scope to app code while excluding library noise:

```bash
$UV fw-calltree \
  --callgraph callgraph.json \
  --class com.example.app.OrderController \
  --method handleGet \
  --pattern '^com\.example\.' \
  > controller-calltree.json
```

Inspect nodes and edges:

```bash
jq '.nodes | keys[:10]' calltree.json
jq '.calls[:10]' calltree.json
```

### `calltree-print` — ASCII rendering of flat graphs

Render `fw-calltree` output:

```bash
$UV calltree-print --input calltree.json
```

Pipe from `fw-calltree`:

```bash
$UV fw-calltree \
  --callgraph callgraph.json \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  | $UV calltree-print
```

### `calltree-to-dot` — DOT/SVG/PNG for flat graphs

Write DOT:

```bash
$UV calltree-to-dot --input calltree.json --output calltree.dot
```

Write SVG:

```bash
$UV calltree-to-dot --input calltree.json --svg --output calltree.svg
```

Write PNG:

```bash
$UV calltree-to-dot --input calltree.json --png --output calltree.png
```

Pipe from `fw-calltree`:

```bash
$UV fw-calltree \
  --callgraph callgraph.json \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  | $UV calltree-to-dot --svg --output calltree.svg
```

Use the same renderer for backward graphs:

```bash
$UV rev-calltree \
  --call-graph callgraph.json \
  --to-class com.example.app.JdbcOrderRepository \
  --to-line 7 \
  | $UV calltree-to-dot --svg --output backward.svg
```

Use the same renderer for `jspmap` output:

```bash
$UV jspmap \
  --jsps path/to/jsps \
  --faces-config path/to/faces-config.xml \
  --call-graph callgraph.json \
  --dao-pattern 'Repository$' \
  | $UV calltree-to-dot --svg --output jspmap.svg
```

### `ftrace-inter-slice` — Interprocedural tree slicing

Keep only paths reaching a target:

```bash
$UV ftrace-inter-slice \
  --input forward.json \
  --to com.example.app.JdbcOrderRepository \
  --to-line 7 \
  --output sliced-to-dao.json
```

Cut a subtree from a specific class:

```bash
$UV ftrace-inter-slice \
  --input forward.json \
  --from com.example.app.OrderService \
  --from-line 17 \
  --output sliced-from-service.json
```

Slice from one point to another:

```bash
$UV ftrace-inter-slice \
  --input forward.json \
  --from com.example.app.OrderService \
  --from-line 17 \
  --to com.example.app.JdbcOrderRepository \
  --to-line 7 \
  --output sliced-path.json
```

Pipe from `xtrace`:

```bash
$B xtrace \
  --call-graph callgraph.json \
  --from com.example.app.OrderService \
  --from-line 17 \
  | $UV ftrace-inter-slice --to com.example.app.JdbcOrderRepository --to-line 7 \
  > sliced.json
```

### `ftrace-intra-slice` — Intra-method CFG slicing

Slice one method between two source lines:

```bash
$UV ftrace-intra-slice \
  --input forward.json \
  --method "<com.example.app.OrderService: java.lang.String processOrder(int)>" \
  --from-line 17 \
  --to-line 23 \
  --output intra.json
```

Run after pruning the trace interprocedurally:

```bash
$UV ftrace-inter-slice \
  --input forward.json \
  --from com.example.app.OrderService \
  --from-line 17 \
  --output sliced-service.json

$UV ftrace-intra-slice \
  --input sliced-service.json \
  --method "<com.example.app.OrderService: java.lang.String processOrder(int)>" \
  --from-line 17 \
  --to-line 23 \
  --output intra.json
```

### `ftrace-expand-refs` — Inline `ref` bodies

Expand a sliced trace:

```bash
$UV ftrace-expand-refs --input sliced-path.json --output expanded.json
```

Expand the raw forward trace:

```bash
$UV ftrace-expand-refs --input forward.json --output expanded-full.json
```

Pipe from the slicer:

```bash
$UV ftrace-inter-slice \
  --input forward.json \
  --to com.example.app.JdbcOrderRepository \
  --to-line 7 \
  | $UV ftrace-expand-refs \
  > expanded.json
```

### `ftrace-semantic` — Semantic CFG normalization

Build semantic JSON from an expanded trace:

```bash
$UV ftrace-semantic --input expanded.json --output semantic.json
```

Pipe directly from expansion:

```bash
$UV ftrace-expand-refs --input sliced-path.json \
  | $UV ftrace-semantic \
  > semantic.json
```

Inspect top-level structure:

```bash
jq 'keys' semantic.json
```

### `ftrace-validate` — Validate semantic graph output

Validate and print the result:

```bash
$UV ftrace-validate --input semantic.json
```

Validate a piped build:

```bash
$UV ftrace-expand-refs --input sliced-path.json \
  | $UV ftrace-semantic \
  | $UV ftrace-validate
```

### `ftrace-semantic-to-dot` — DOT/SVG/PNG for semantic graphs

Write DOT:

```bash
$UV ftrace-semantic-to-dot --input semantic.json --output trace.dot
```

Write SVG:

```bash
$UV ftrace-semantic-to-dot --input semantic.json --output trace.svg
```

Write PNG:

```bash
$UV ftrace-semantic-to-dot --input semantic.json --output trace.png
```

Use orthogonal edges:

```bash
$UV ftrace-semantic-to-dot \
  --input semantic.json \
  --output trace.svg \
  --splines ortho
```

Pipe directly from semantic generation:

```bash
$UV ftrace-expand-refs --input sliced-path.json \
  | $UV ftrace-semantic \
  | $UV ftrace-semantic-to-dot --output trace.svg
```

### `jspmap` — JSP EL to Java call graph mapping

Basic:

```bash
$UV jspmap \
  --jsps path/to/jsps \
  --faces-config path/to/faces-config.xml \
  --call-graph callgraph.json \
  --dao-pattern 'Repository$' \
  --output jspmap.json
```

Restrict the Java side of the graph:

```bash
$UV jspmap \
  --jsps path/to/jsps \
  --faces-config path/to/faces-config.xml \
  --call-graph callgraph.json \
  --dao-pattern 'Repository$' \
  --pattern '^com\.example\.' \
  --output jspmap.json
```

Analyze one JSP only:

```bash
$UV jspmap \
  --jsps path/to/jsps \
  --faces-config path/to/faces-config.xml \
  --call-graph callgraph.json \
  --dao-pattern 'Repository$' \
  --jsp admin/orders.jsp \
  --output admin-orders.json
```

Analyze one JSP plus its transitive includes:

```bash
$UV jspmap \
  --jsps path/to/jsps \
  --faces-config path/to/faces-config.xml \
  --call-graph callgraph.json \
  --dao-pattern 'Repository$' \
  --jsp admin/orders.jsp \
  --recurse \
  --output admin-orders-recursive.json
```

Allow `.jspx` too:

```bash
$UV jspmap \
  --jsps path/to/jsps \
  --faces-config path/to/faces-config.xml \
  --call-graph callgraph.json \
  --dao-pattern 'Repository$' \
  --extensions jsp,jspf,xhtml,jspx \
  --output jspmap.json
```

Render the result:

```bash
$UV calltree-to-dot --input jspmap.json --svg --output jspmap.svg
```

## End-to-End Recipes

### Build everything from scratch

```bash
$B buildcg --output callgraph.json
$B dump com.example.app.OrderService --output order-service.json
$B xtrace --call-graph callgraph.json --from com.example.app.OrderService --from-line 17 --output forward.json
```

### Forward trace to SVG

```bash
$B xtrace \
  --call-graph callgraph.json \
  --from com.example.app.OrderService \
  --from-line 17 \
  | $UV ftrace-inter-slice --to com.example.app.JdbcOrderRepository --to-line 7 \
  | $UV ftrace-expand-refs \
  | $UV ftrace-semantic \
  | $UV ftrace-semantic-to-dot --output trace.svg
```

### Forward trace to semantic JSON and validation

```bash
$B xtrace \
  --call-graph callgraph.json \
  --from com.example.app.OrderService \
  --from-line 17 \
  | $UV ftrace-inter-slice --to com.example.app.JdbcOrderRepository --to-line 7 \
  | $UV ftrace-expand-refs \
  | $UV ftrace-semantic \
  > semantic.json

$UV ftrace-validate --input semantic.json
```

### Backward trace to pretty text and SVG

```bash
$UV rev-calltree \
  --call-graph callgraph.json \
  --to-class com.example.app.JdbcOrderRepository \
  --to-line 7 \
  > backward.json

$UV frames-print --input backward.json --output backward.txt
$UV calltree-to-dot --input backward.json --svg --output backward.svg
```

### Method-level call tree to text and SVG

```bash
$UV fw-calltree \
  --callgraph callgraph.json \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern '^com\.example\.' \
  > calltree.json

$UV calltree-print --input calltree.json
$UV calltree-to-dot --input calltree.json --svg --output calltree.svg
```
