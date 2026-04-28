# Bytecode Tools — Cheatsheet

All Java commands go through `scripts/bytecode.sh`. Python tools run via `uv --directory python run <tool>`.

```bash
B() { scripts/bytecode.sh --prefix com.example. path/to/classes "$@"; }
UV() { uv --directory python run "$@"; }
```

---

## Java CLI

### Global options (before subcommand)

| Option | Required | Description |
|--------|----------|-------------|
| `--prefix <pkg.>` | No | Limit analysis to FQCNs starting with this string |
| `<classpath>` | Yes | Colon-separated `.class` directories or jars |

---

### `buildcg` — Build whole-program call graph

```bash
$B buildcg --output callgraph.json
```

| Option | Required | Description |
|--------|----------|-------------|
| `--output <file>` | No | Write JSON to file (default: stdout) |

Output: `{ "<sig>": ["<callee-sig>", ...], ... }`. Compiler-generated bridge methods are collapsed automatically. Rebuild whenever classes change.

---

### `dump` — List methods with line ranges

```bash
$B dump com.example.app.OrderService
$B dump com.example.app.OrderService --output dump.json
```

| Argument | Required | Description |
|----------|----------|-------------|
| `<FQCN>` | Yes | Fully qualified class name |
| `--output <file>` | No | Write JSON to file (default: stdout) |

Use `jq` to extract line numbers for use with `xtrace`/`frames`:
```bash
jq '.methods[] | select(.method == "processOrder") | .lineStart' dump.json
```

---

### `trace` — Intraprocedural path trace

```bash
$B trace com.example.app.OrderService 42 87
$B trace com.example.app.OrderService 42 87 --output trace.json
```

| Argument | Required | Description |
|----------|----------|-------------|
| `<FQCN>` | Yes | Fully qualified class name |
| `<from-line>` | Yes | Source line to trace from |
| `<to-line>` | Yes | Source line to trace to |
| `--output <file>` | No | Write JSON to file (default: stdout) |

Single method only. For cross-method traces use `xtrace`.

---

### `xtrace` — Forward interprocedural trace

```bash
$B xtrace \
  --call-graph callgraph.json \
  --from com.example.app.OrderController \
  --from-line 42 \
  --output forward.json
```

With filter:
```bash
$B xtrace \
  --call-graph callgraph.json \
  --from com.example.app.OrderController \
  --from-line 42 \
  --filter config/filter.json \
  --output forward.json
```

| Option | Required | Description |
|--------|----------|-------------|
| `--call-graph <file>` | Yes | Call graph JSON from `buildcg` |
| `--from <FQCN>` | Yes | Entry-point class |
| `--from-line <N>` | Yes | Source line in `--from` class |
| `--filter <file>` | No | JSON with `allow`/`stop` prefix arrays |
| `--output <file>` | No | Write JSON to file (default: stdout) |

Output: `{ "trace": <root-body>, "refIndex": { "<sig>": <body>, ... } }`. Non-root callees are emitted as lightweight `ref` leaves; expand them with `ftrace-expand-refs`.

---

### `frames` — Backward interprocedural trace

Find all call chains that reach a target method:
```bash
$B frames \
  --call-graph callgraph.json \
  --to com.example.app.JdbcOrderRepository \
  --to-line 7 \
  --output backward.json
```

Constrain to a known entry point:
```bash
$B frames \
  --call-graph callgraph.json \
  --from com.example.app.OrderController \
  --from-line 15 \
  --to com.example.app.JdbcOrderRepository \
  --to-line 7 \
  --output backward.json
```

| Option | Required | Description |
|--------|----------|-------------|
| `--call-graph <file>` | Yes | Call graph JSON from `buildcg` |
| `--to <FQCN>` | Yes | Target class (find callers of this) |
| `--to-line <N>` | Yes | Source line in `--to` class |
| `--from <FQCN>` | No | Constrain to a specific entry-point class |
| `--from-line <N>` | No | Source line in `--from` class (required with `--from`) |
| `--depth <N>` | No | Max backward BFS depth (default: 50) |
| `--max-chains <N>` | No | Max call chains to return (default: 50) |
| `--output <file>` | No | Write JSON to file (default: stdout) |

Pretty-print the result with `frames-print`.

---

## Python Tools

All tools read stdin when `--input` is omitted, write stdout when `--output` is omitted — composable as Unix filters.

---

### `ftrace-slice` — Slice a subtree from a forward trace

```bash
# --from only: subtree rooted at the matching node
$UV ftrace-slice --from com.example.app.ExceptionService --input forward.json

# --to only: prune tree so only paths reaching target remain; target is a leaf
$UV ftrace-slice --to com.example.app.JdbcOrderRepository

# --from + --to: subtree from --from, then pruned to --to
$UV ftrace-slice \
  --from com.example.app.OrderController \
  --to com.example.app.JdbcOrderRepository \
  --output sliced.json
```

| Option | Required | Description |
|--------|----------|-------------|
| `--from <FQCN>` | One of `--from`/`--to` | FQCN of start node |
| `--from-line <N>` | No | Line within `--from` class to narrow match (default: 0 = match any) |
| `--to <FQCN>` | One of `--from`/`--to` | FQCN of target node (becomes a leaf) |
| `--to-line <N>` | No | Line within `--to` class to narrow match (default: 0 = match any) |
| `--input <file>` | No | Full ftrace JSON (default: stdin) |
| `--output <file>` | No | Output file (default: stdout) |

---

### `ftrace-expand-refs` — Inline ref bodies from refIndex

```bash
$UV ftrace-expand-refs --input sliced.json --output expanded.json
# or piped:
$UV ftrace-slice ... | $UV ftrace-expand-refs
```

| Option | Required | Description |
|--------|----------|-------------|
| `--input <file>` | No | SlicedTrace JSON (default: stdin) |
| `--output <file>` | No | Output file (default: stdout) |

---

### `ftrace-semantic` — Build semantic graph

```bash
$UV ftrace-semantic --input expanded.json --output semantic.json
```

| Option | Required | Description |
|--------|----------|-------------|
| `--input <file>` | No | Expanded ftrace JSON (default: stdin) |
| `--output <file>` | No | Output file (default: stdout) |

---

### `ftrace-to-dot` — Render as DOT / SVG / PNG

```bash
$UV ftrace-to-dot --input semantic.json --output trace.svg
$UV ftrace-to-dot --input semantic.json --output trace.dot
$UV ftrace-to-dot --input semantic.json                     # DOT to stdout
$UV ftrace-to-dot --input semantic.json --output trace.svg --splines ortho
```

| Option | Required | Description |
|--------|----------|-------------|
| `--input <file>` | No | Semantic JSON (default: stdin) |
| `--output <file>` | No | `.dot`, `.svg`, or `.png` (default: DOT to stdout) |
| `--splines <style>` | No | Edge routing: `spline`, `ortho`, `curved`, `line`, `polyline` |

---

### `ftrace-validate` — Validate semantic graph structure

```bash
$UV ftrace-validate --input semantic.json
```

| Option | Required | Description |
|--------|----------|-------------|
| `--input <file>` | No | Semantic JSON (default: stdin) |
| `--output <file>` | No | Output JSON (default: stdout) |

Exits non-zero if invariants are violated.

---

### `frames-print` — Pretty-print backward trace chains

```bash
$UV frames-print --input backward.json
$UV frames-print --input backward.json --output chains.txt
# or piped directly from frames:
$B frames --call-graph callgraph.json --to com.example.app.JdbcOrderRepository --to-line 7 \
  | $UV frames-print
```

| Option | Required | Description |
|--------|----------|-------------|
| `--input <file>` | No | Frames JSON (default: stdin) |
| `--output <file>` | No | Output file (default: stdout) |

---

## Full Pipelines

### Forward trace → SVG

```bash
$B xtrace --call-graph callgraph.json \
  --from com.example.app.OrderController --from-line 42 \
| $UV ftrace-slice --to com.example.app.JdbcOrderRepository \
| $UV ftrace-expand-refs \
| $UV ftrace-semantic \
| $UV ftrace-to-dot --output trace.svg
```

### Backward trace → pretty-printed chains

```bash
$B frames --call-graph callgraph.json \
  --to com.example.app.JdbcOrderRepository --to-line 7 \
  --max-chains 200 \
| $UV frames-print
```

### Rebuild call graph then backward trace

```bash
$B buildcg --output callgraph.json
$B frames --call-graph callgraph.json \
  --to com.example.app.JdbcOrderRepository --to-line 7 \
  --output backward.json
$UV frames-print --input backward.json
```
