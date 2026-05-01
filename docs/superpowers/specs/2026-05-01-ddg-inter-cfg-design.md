# ddg-inter-cfg Design

## Goal

Add a new tool, `ddg-inter-cfg`, that consumes the existing flat `fw-calltree` method graph and emits a compound artifact containing:

- the original reachable method nodes
- the original inter-method call edges
- a per-method intraprocedural graph payload for each reachable method, including CFG and DDG edges

This tool is a build-layer artifact generator only. It does **not** implement recursive interprocedural querying yet.

## Scope

### In scope

- Read a flat `fw-calltree` JSON graph from stdin by default, or from `--input`
- Write a compound JSON artifact to stdout by default, or to `--output`
- Preserve top-level method graph compatibility with the existing flat schema:
  - `nodes`
  - `calls`
- Resolve each reachable method signature with SootUp
- Build each method's statement-level CFG/DDG independently
- Emit a per-method graph payload under `ddgs[methodSignature]`

### Out of scope

- Query-time recursive traversal across methods
- Interprocedural summary edges such as actual-arg → formal-param
- Whole-repo schema migration from top-level `calls` to `edges`
- Replacing or modifying `fw-calltree`, `rev-calltree`, `jspmap`, `calltree-print`, or `calltree-to-dot`
- Heap/alias-sensitive interprocedural dependence

## Why `fw-calltree`

`fw-calltree` already provides the reachable method universe and caller→callee relationships from an entry point. That is enough to drive the build layer:

1. discover reachable methods
2. resolve each reachable method body independently
3. compute CFG/DDG per method
4. package everything into one artifact

`fw-calltree` is method-level only. It is not an interprocedural CFG. That is acceptable here because `ddg-inter-cfg` is deliberately modeling:

- a top-level method call graph
- plus per-method intraprocedural dependency graphs

The later query layer can compose across these graphs.

## Tool Contract

### Input

`ddg-inter-cfg` consumes the existing `fw-calltree` flat graph shape:

```json
{
  "nodes": {
    "<com.example.A: void foo()>": {
      "node_type": "java_method",
      "class": "com.example.A",
      "method": "foo",
      "methodSignature": "<com.example.A: void foo()>"
    }
  },
  "calls": [
    {
      "from": "<com.example.A: void foo()>",
      "to": "<com.example.B: void bar()>",
      "callSiteLine": 42,
      "edge_info": {}
    }
  ],
  "metadata": {
    "tool": "calltree"
  }
}
```

Only the method signatures in `nodes` are analyzed. `calls` is preserved at the top level for compatibility with the existing flat-graph family.

### Output

The output extends the flat input shape with a `ddgs` map:

```json
{
  "nodes": { "...": {} },
  "calls": [ { "...": "..." } ],
  "ddgs": {
    "<com.example.A: void foo()>": {
      "nodes": [ { "...": "..." } ],
      "edges": [ { "...": "..." } ],
      "entry_stmt_ids": [ "s0" ],
      "return_stmt_ids": [ "s7" ],
      "callsite_stmt_ids": [ "s3" ]
    }
  },
  "metadata": {
    "tool": "ddg-inter-cfg"
  }
}
```

## Unix I/O Semantics

The tool follows the same Unix-style conventions used across the repo's Python transformers:

- stdin when `--input` is omitted
- stdout when `--output` is omitted
- errors and progress messages to stderr

CLI shape:

```bash
ddg-inter-cfg [--input PATH] [--output PATH]
```

Examples:

```bash
uv --directory python run fw-calltree \
  --callgraph ../callgraph.json \
  --class com.example.app.OrderService \
  --method processOrder \
  --pattern 'com\.example' \
  | scripts/bytecode.sh --prefix com.example. "$CP" ddg-inter-cfg
```

```bash
scripts/bytecode.sh --prefix com.example. "$CP" ddg-inter-cfg \
  --input calltree.json \
  --output ddg-inter-cfg.json
```

Implementation note: the tool is expected to live on the Java side because it must resolve methods and build DDGs with SootUp. It therefore needs explicit support for reading JSON from stdin and writing JSON to stdout/file, rather than assuming path-only inputs like `xtrace`.

## Top-Level Schema

### `nodes`

Copied through from the input `fw-calltree` graph unchanged.

Keys are method signatures.

Values are method metadata records such as:

- `node_type`
- `class`
- `method`
- `methodSignature`
- `lineStart`
- `lineEnd`
- `sourceLineCount`

### `calls`

Copied through from the input `fw-calltree` graph unchanged.

This field intentionally remains named `calls` to preserve compatibility with the existing flat-graph tools. It is **not** renamed to `edges` in this tool.

Each entry is a method-level call edge:

```json
{
  "from": "<caller-sig>",
  "to": "<callee-sig>",
  "callSiteLine": 42,
  "edge_info": {}
}
```

Cycle and filtered flags, if present in the input, are preserved.

### `ddgs`

Map keyed by method signature:

```json
{
  "<com.example.A: void foo()>": {
    "nodes": [],
    "edges": [],
    "entry_stmt_ids": [],
    "return_stmt_ids": [],
    "callsite_stmt_ids": []
  }
}
```

This is where the new graph content lives.

### `metadata`

At minimum:

```json
{
  "tool": "ddg-inter-cfg"
}
```

Likely additional keys:

- `inputTool` — copied from input metadata when present
- `methodCount`
- `ddgCount`

## Per-Method DDG Payload

Each `ddgs[methodSignature]` entry contains a self-contained statement graph for that method.

### `nodes`

Statement-level nodes only in v1.

Example:

```json
{
  "id": "s3",
  "node_type": "stmt",
  "stmt": "result = virtualinvoke this.<... transform(java.lang.String)>(order)",
  "line": 18,
  "kind": "assign_invoke"
}
```

Suggested fields:

- `id` — statement-local stable ID such as `s0`, `s1`, ...
- `node_type` — always `"stmt"` in v1
- `stmt` — Jimple statement string
- `line` — source line when available, else `-1`
- `kind` — coarse statement classification

Suggested `kind` values:

- `identity`
- `assign`
- `assign_invoke`
- `invoke`
- `if`
- `return`
- `return_void`
- `throw`
- `goto`
- `switch`
- `other`

Optional enrichments when easy to compute:

- `parameterIndex` for `@parameterN` identity statements
- `isThis` for `@this`
- `call.targetMethodSignature` for invoke statements

### `edges`

Combined intra-method edge list for both CFG and DDG edges.

Edges are distinguished by `edge_info.kind`.

CFG example:

```json
{
  "from": "s3",
  "to": "s4",
  "edge_info": {
    "kind": "cfg"
  }
}
```

DDG example:

```json
{
  "from": "s3",
  "to": "s7",
  "edge_info": {
    "kind": "ddg",
    "label": "ddg_next"
  }
}
```

Optional CFG enrichments:

- `branch: "true"` / `branch: "false"` for conditional edges when recoverable
- `exceptional: true` for exceptional control-flow edges

No top-level per-method split into `cfgEdges` and `ddgEdges` is planned. A single `edges` list keeps the per-method graph uniform and future-proof.

### Helper ID Lists

These are indexing conveniences for the future query layer.

#### `entry_stmt_ids`

Statement IDs corresponding to entry/identity statements, typically:

- `this := @this`
- `param := @parameterN`

#### `return_stmt_ids`

Statement IDs whose statements are:

- `return ...`
- optionally `returnvoid`

#### `callsite_stmt_ids`

Statement IDs representing invoke sites:

- `invoke`
- `assign_invoke`

These make later recursive composition much easier without rescanning every node.

## Statement ID Strategy

Statement IDs only need to be unique within one method payload.

Recommended strategy:

- use the method-local statement order from `StmtGraph.getStmts()`
- assign IDs `s0`, `s1`, `s2`, ...

Why this is sufficient:

- each method payload is already keyed by `methodSignature`
- the query layer can qualify a node as `(methodSignature, stmtId)` if it needs a global identifier
- local IDs are shorter and easier to inspect in JSON

No global statement ID scheme is required in v1.

## Graph Construction

For each method signature in top-level `nodes`:

1. Resolve the `SootMethod`
2. Get the method body and `StmtGraph`
3. Enumerate statements and assign local statement IDs
4. Build per-statement node records
5. Emit CFG edges from `StmtGraph.successors(stmt)`
6. Emit exceptional CFG edges from `StmtGraph.exceptionalSuccessors(stmt)` if desired in v1
7. Build DDG edges from `new DdgCreator().createGraph(method)`
8. Collect helper lists:
   - entry statements
   - return statements
   - callsites

The top-level `calls` array is not used to construct intraprocedural DDGs. It exists to preserve the inter-method skeleton around the method-local graphs.

## CFG Edge Semantics

`edge_info.kind = "cfg"` means execution can proceed from the source statement to the destination statement.

This is control flow, not value flow.

Examples:

- sequential fallthrough
- branch target
- exceptional successor

## DDG Edge Semantics

`edge_info.kind = "ddg"` means the source statement defines a value that influences the destination statement.

This is data dependence, not execution order.

Examples:

- parameter definition → invoke argument use
- call result assignment → branch condition
- local definition → return statement

In current SootUp output, the DDG label observed is `ddg_next`, so the edge metadata should preserve that label when available.

## Error Handling

Invalid input should fail fast with a clear stderr message and non-zero exit.

Examples:

- malformed JSON
- missing top-level `nodes`
- method signature in `nodes` cannot be resolved on the classpath
- method has no body

Recommended behavior for partial failures:

- default to fail-fast in v1
- do not emit a partially complete artifact unless an explicit future flag asks for best-effort behavior

## Compatibility

### Preserved

- top-level `nodes`
- top-level `calls`
- existing flat-graph semantics at the method level

### Not introduced yet

- top-level `edges` replacing `calls`
- interprocedural data-dependence edges
- stitched caller/callee statement graph

This keeps `ddg-inter-cfg` narrowly focused and avoids forcing schema changes across the rest of the flat-graph tool family.

## Non-Goals for v1

The following are explicitly deferred:

- actual-arg → formal-param edges
- callee-return → caller-assignment edges
- caller-receiver → callee-`this` edges
- field/heap/alias-sensitive summaries
- recursive or fixpoint interprocedural slicing
- DOT/SVG rendering for the new artifact

These belong to the future query/composition layer.

## Minimal Test Plan

### Shape test

Given a small `fw-calltree` input with one or two methods:

- output preserves top-level `nodes`
- output preserves top-level `calls`
- output contains `ddgs`
- output contains a payload for each method signature in `nodes`

### Method payload test

For `OrderService.processOrder(int)`:

- statement nodes are present
- at least one `cfg` edge exists
- at least one `ddg` edge exists
- `return_stmt_ids` is non-empty
- `callsite_stmt_ids` is non-empty

### Unix I/O test

- stdin → stdout works
- `--input` works
- `--output` works

### Error test

- missing `nodes` fails with non-zero exit
- unresolved method signature fails with non-zero exit

## File Impact

Expected implementation area:

- new Java command class under `tools.bytecode.cli`
- new Java builder/serializer classes under `tools.bytecode`
- CLI registration in `CLI.java`
- tests under `java/src/test/java/tools/bytecode/` and/or `tools/bytecode/cli/`

No existing flat-graph producers or consumers need to change for this feature.
