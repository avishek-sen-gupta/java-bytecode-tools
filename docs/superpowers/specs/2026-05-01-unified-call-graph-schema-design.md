# Design: Unified Call Graph Schema

## Problem

`calltree` and `frames` produce different JSON schemas despite both being interprocedural call graph traversals. Their consumers (`calltree-to-dot`, `frames-print`) are therefore tool-specific. The goal is a single flat graph schema that both tools emit and both consumers read.

Additionally, `frames` (Java, SootUp-based) duplicates analysis that `buildcg` already performs — method line ranges can be derived once in `buildcg` and reused, allowing `frames` to be rewritten as a pure Python script with no SootUp dependency.

## Unified Output Schema

Both `calltree` and `frames` emit:

```json
{
  "nodes": {
    "<sig>": {
      "class": "com.example.Foo",
      "method": "bar",
      "methodSignature": "<com.example.Foo: void bar(int)>",
      "lineStart": 42,
      "lineEnd": 67,
      "sourceLineCount": 26
    }
  },
  "calls": [
    { "from": "<caller-sig>", "to": "<callee-sig>", "callSiteLine": 55 },
    { "from": "<caller-sig>", "to": "<callee-sig>", "cycle": true },
    { "from": "<caller-sig>", "to": "<callee-sig>", "filtered": true }
  ],
  "metadata": {
    "tool": "calltree",
    "entryClass": "com.example.Foo",
    "entryMethod": "bar"
  }
}
```

For `frames`, `metadata` uses `toClass`, `toLine`, and optionally `fromClass`, `fromLine` instead of `entryClass`/`entryMethod`.

### Node fields

| Field | Present in calltree | Present in frames |
|-------|--------------------|--------------------|
| `class` | yes | yes |
| `method` | yes | yes |
| `methodSignature` | yes | yes |
| `lineStart` | yes (from `methodLines`) | yes (from `methodLines`) |
| `lineEnd` | yes | yes |
| `sourceLineCount` | yes | yes |

### Call edge flags

- No flag: normal call edge
- `cycle: true`: callee is an ancestor in the current DFS path
- `filtered: true`: callee is out of scope (no `nodes` entry emitted for it)

Roots are nodes with no incoming `calls` entries. Leaves are nodes with no outgoing `calls` entries (or only filtered/cycle edges).

## Changes by Component

### 1. `buildcg` — add `methodLines`

`CallGraphBuilder` already iterates every project `SootMethod` to build `callees`. Extend that loop to collect `entryLine`/`exitLine` per method and emit:

```json
{
  "callees":  { "<sig>": ["<callee-sig>", ...] },
  "callsites": { "<caller-sig>": { "<callee-sig>": lineNumber } },
  "methodLines": { "<sig>": { "lineStart": 42, "lineEnd": 67 } }
}
```

`jspmap`, `ForwardTracer` (`xtrace`), and any other existing consumers of `callees`/`callsites` are unaffected — `methodLines` is additive.

### 2. `calltree.py` — emit unified schema

Currently emits `{trace, refIndex}`. Changes:

- Read `methodLines` from call graph JSON; populate `lineStart`/`lineEnd`/`sourceLineCount` on each node entry.
- Emit `{nodes, calls, metadata}` instead of `{trace, refIndex}`.
- `ref` deduplication via `refIndex` is replaced by the flat `nodes` dict (naturally deduplicated by sig key).
- `cycle`/`filtered` move from per-node flags to per-edge flags on `calls` entries.

### 3. `frames.py` — new Python script, replaces Java `FramesCommand`

Inputs: `--call-graph <path>`, `--to-class <FQCN>`, `--to-line <n>`, optionally `--from-class <FQCN>`, `--from-line <n>`, `--max-depth <n>`, `--max-chains <n>`

Algorithm:

1. Load call graph JSON; read `callees`, `callsites`, `methodLines`.
2. Find target sig: scan `methodLines` for a sig whose class component matches `toClass` and whose `[lineStart, lineEnd]` range contains `toLine`.
3. Optionally find from-sig the same way.
4. Build reverse map: invert `callees` → `callers: { callee-sig: [caller-sig, ...] }`.
5. BFS backward from target sig up to `--max-depth` levels; collect reachable methods. If `--from-class` given, stop at from-sig. Otherwise stop at methods with no callers.
6. DFS from each entry point to enumerate distinct chains up to `--max-chains`; look up `callSiteLine` from `callsites`.
7. Emit `{nodes, calls, metadata}`.

### 4. `FramesCommand.java` and `BackwardTracer.java` — deleted

`frames` is now Python-only. Both Java classes are removed.

### 5. `calltree-to-dot.py` — rewrite to consume `{nodes, calls}`

- Render each entry in `nodes` as a DOT node (label = `ShortClass.method`).
- Render each entry in `calls` (excluding `filtered: true` — those are omitted entirely) as a DOT edge.
- Cycle edges rendered with a distinct style (dashed).
- Roots (nodes with no incoming calls) optionally get a distinct shape.

### 6. `frames_print.py` — rewrite to consume `{nodes, calls}`

- Build adjacency from `calls` list.
- Find roots: nodes with no incoming call edges.
- DFS from each root; print each root-to-leaf path as a chain with indentation and callsite lines, matching current visual output.

### 7. Tests and E2E

- `BuildFrameMapTest` and any test exercising `BackwardTracer` directly: deleted.
- New Python tests for `frames.py` covering: target resolution, backward BFS, chain enumeration, cycle handling.
- `test_calltree_to_dot.py`: update fixtures to new schema.
- `test-fixtures/run-e2e.sh`: update `frames` invocation from Java CLI to Python script.

## Out of Scope

- `xtrace` and the `ftrace-*` pipeline: untouched. `xtrace` is a heavier tool with its own envelope schema (`{trace, refIndex}` with per-method `blocks`/`edges`/`traps`) consumed by `ftrace-semantic`, `ftrace-validate`, etc.
- `jspmap`: reads `callees` only; no changes needed.
- `dump`, `trace`: unrelated to call graph.
