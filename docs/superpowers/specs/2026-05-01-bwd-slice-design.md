# Backward Interprocedural Data Dependency Slice Design

## Goal

Add a `bwd-slice` experiment tool that, given a `ddg-inter-cfg` artifact, a method signature, and a Jimple local variable name, performs a recursive backward data dependency slice across method boundaries and emits a subgraph of all upstream dependencies.

## Scope

### In scope

- Read a `ddg-inter-cfg` JSON artifact from `--input` or stdin
- Accept a seed: `--method <sig>` and `--local-var <name>`
- Walk backward through intra-method DDG edges (from the artifact)
- Cross method boundaries at parameter identity statements and return values
- Emit a dependency subgraph to stdout or `--output`

### Out of scope

- Heap/alias-sensitive analysis
- Field-level dependency tracking
- DOT/SVG rendering
- Modifying `ddg-inter-cfg` or any upstream tool

## Tool Contract

### Input

A `ddg-inter-cfg` artifact:

```json
{
  "nodes": { "<sig>": { ... } },
  "calls": [ { "from": "<sig>", "to": "<sig>", ... } ],
  "ddgs": {
    "<sig>": {
      "nodes": [ { "id": "s0", "stmt": "...", "line": 10, "kind": "identity" } ],
      "edges": [ { "from": "s0", "to": "s1", "edge_info": { "kind": "ddg" } } ],
      "entry_stmt_ids": [ "s0" ],
      "return_stmt_ids": [ "s7" ],
      "callsite_stmt_ids": [ "s3" ]
    }
  }
}
```

### Output

```json
{
  "seed": { "method": "<sig>", "local_var": "r0" },
  "nodes": [
    { "method": "<sig>", "stmtId": "s3", "stmt": "...", "local_var": "r0", "line": 18, "kind": "assign_invoke" }
  ],
  "edges": [
    {
      "from": { "method": "<sig>", "stmtId": "s1" },
      "to":   { "method": "<sig>", "stmtId": "s3" },
      "edge_info": { "kind": "ddg" }
    },
    {
      "from": { "method": "<callee-sig>", "stmtId": "s6" },
      "to":   { "method": "<caller-sig>", "stmtId": "s5" },
      "edge_info": { "kind": "return" }
    },
    {
      "from": { "method": "<caller-sig>", "stmtId": "s5" },
      "to":   { "method": "<callee-sig>", "stmtId": "s0" },
      "edge_info": { "kind": "param", "paramIndex": 0 }
    }
  ]
}
```

### Edge kinds

- `ddg` — intra-method data dependency (from definition stmt to dependent stmt)
- `param` — call site argument flows to formal parameter identity stmt in callee
- `return` — callee return stmt flows to call site assignment LHS in caller

### Node fields

- `method` — method signature (scopes the `stmtId`)
- `stmtId` — local statement ID from the `ddg-inter-cfg` payload (e.g. `s3`)
- `stmt` — Jimple statement text
- `local_var` — the specific local variable being tracked at this node
- `line` — source line number, or `-1`
- `kind` — statement kind from the artifact

## Traversal Algorithm

Worklist BFS. Each item is `(methodSig, stmtId, localVar)`.

**Seed**: find all stmt nodes in `ddgs[methodSig]` where `local_var` appears as the defined variable (left-hand side of assignment or identity). Enqueue each as the starting frontier.

**Within a method**: for a given stmt `s` tracking `localVar`:
1. Find all DDG edges in `ddgs[methodSig].edges` where `to == s.id` and `edge_info.kind == "ddg"`.
2. For each such edge, resolve the source stmt `p`. Identify which local `p` defines (its LHS). Enqueue `(methodSig, p.id, p.local)`.
3. Emit a `ddg` edge from `p` to `s`.

**Cross boundary — parameter**:
When `s` is in `entry_stmt_ids` and is a `@parameterN` identity stmt:
1. Extract parameter index N from `s.stmt`.
2. Look in top-level `calls` for edges where `to == methodSig`.
3. For each caller, find the call site stmt in `ddgs[callerSig]` whose `call.targetMethodSignature == methodSig`.
4. Extract the Nth argument local from that call site stmt.
5. Enqueue `(callerSig, callSiteStmtId, argLocal)`.
6. Emit a `param` edge from call site to `s`.

**Cross boundary — return value**:
When the seed stmt is a call site assignment (`kind == "assign_invoke"`):
1. Identify the callee method signature from the stmt's `call.targetMethodSignature`.
2. Find `return_stmt_ids` in `ddgs[calleeSig]`.
3. For each return stmt, identify its returned local.
4. Enqueue `(calleeSig, returnStmtId, returnedLocal)`.
5. Emit a `return` edge from the return stmt to the call site.

**Termination**: visited set on `(methodSig, stmtId)`. Stop when worklist is empty.

## Architecture

### `BwdSliceCommand` (`tools.bytecode.cli`)

Picocli subcommand registered in `CLI.java`.

Options:
- `--input <path>` — `ddg-inter-cfg` artifact (stdin if omitted)
- `--output <path>` — result JSON (stdout if omitted)
- `--method <sig>` — seed method signature (required)
- `--local-var <name>` — seed Jimple local variable name (required)

Reads artifact JSON, delegates to `BwdSliceBuilder`, serialises result.

### `BwdSliceBuilder` (`tools.bytecode`)

Pure functional. No SootUp dependency — operates entirely on the parsed JSON artifact.

```
build(Map<String,Object> ddgInterCfg, String methodSig, String localVar)
  → Map<String,Object> slice
```

Internally builds a caller index (inverted `calls` list) on construction for efficient caller lookup.

## CLI Usage

```bash
# Pipeline
fw-calltree ... \
  | bytecode $CP ddg-inter-cfg \
  | bytecode $CP bwd-slice --method "<com.example.app.OrderService: void processOrder(int)>" --local-var "r0"

# With files
bytecode $CP ddg-inter-cfg --input calltree.json --output artifact.json
bytecode $CP bwd-slice --input artifact.json \
  --method "<com.example.app.OrderService: void processOrder(int)>" \
  --local-var "r0"
```

## Testing

### Unit: `BwdSliceBuilderTest`

- Single-method arithmetic slice: two paths from `a` and `b` converging at `$i0 = a + b` — verify both upstream nodes present and two incoming edges at `s1`.
- Cross-method parameter slice: seed in callee, verify param edge to caller call site.
- Cross-method return slice: seed is a call site assignment, verify return edge from callee return stmt.
- Cycle safety: a recursive or mutually recursive call graph does not loop forever.
- Seed local not found: returns empty nodes and edges.

### Integration: `test_bwd_slice.sh`

Run against test fixtures (`OrderService`). Assert:
- Output contains `nodes` and `edges`.
- Seed node is present.
- At least one inter-method edge exists.

## File Impact

- Create: `java/src/main/java/tools/bytecode/BwdSliceBuilder.java`
- Create: `java/src/main/java/tools/bytecode/cli/BwdSliceCommand.java`
- Modify: `java/src/main/java/tools/bytecode/cli/CLI.java` — register `BwdSliceCommand`
- Create: `java/src/test/java/tools/bytecode/BwdSliceBuilderTest.java`
- Create: `test-fixtures/tests/test_bwd_slice.sh`
