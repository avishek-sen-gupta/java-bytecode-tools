# ftrace-slice --from/--to Design

## Context

`ftrace-slice` currently requires users to write a jq query string to select a subtree from a forward trace. This is error-prone, requires jq knowledge, and cannot express path-finding between two methods. This design replaces `--query` with domain-specific `--from`/`--to` flags that express intent directly and enable call-path extraction.

## CLI

Remove `--query`. Add:

```
--from CLASS       FQCN of start node  (e.g. com.example.app.ComplexService)
--from-line N      optional; narrows match to the method whose body contains line N
--to CLASS         FQCN of target node
--to-line N        optional; narrows match to the method whose body contains line N
```

At least one of `--from` / `--to` must be provided. `--from-line` / `--to-line` are always optional.

## Modes

| Flags | Behaviour |
|-------|-----------|
| `--from` only | DFS into trace tree, find first node matching class (+line), return its full subtree as `SlicedTrace`. Same semantics as today's jq subtree slice. |
| `--from + --to` | DFS to `--from` node, then prune its children to only branches reaching `--to`. Stop at `--to` (children stripped). |
| `--to` only | Same prune applied from the trace root. |

Multiple paths to `--to` are preserved as a merged branching tree (not separate traces). `--to` node appears as a leaf with no children in the output.

## Matching

```python
def matches(node: MethodCFG, class_name: str, line: int) -> bool:
    """Match node by class name and optionally by line within method body.

    line == 0 means not provided — matches any line range.
    lineStart/lineEnd are xtrace output fields present in the JSON but not
    declared in the TypedDict (total=False).
    """
    class_match = node.get("class", "") == class_name
    if line == 0:
        return class_match
    return class_match and node.get("lineStart", 0) <= line <= node.get("lineEnd", 0)
```

## Core Pure Functions

```
matches(node, class_name, line) → bool
  Node identity predicate.

find_subtree(tree, class_name, line) → list[MethodCFG]
  DFS; returns [node] at first match (full subtree intact), [] if not found.
  Used for --from-only mode.

prune_to_target(node, class_name, line) → list[MethodCFG]
  Returns [node_with_pruned_children] if target is reachable from node, [] otherwise.
  When node itself matches: return [node with children: []].
  Used for --to and --from+--to modes.
```

## Output

`SlicedTrace` format is unchanged:
```json
{ "slice": <MethodCFG subtree>, "refIndex": { sig -> full node } }
```

`refIndex` built identically to today: collect `ref: true` signatures from the pruned slice, resolve against the envelope's refIndex or walk the full tree.

## What Changes

- `ftrace_slice.py`: remove jq subprocess; implement `matches`, `find_subtree`, `prune_to_target`; update `main()` argument parsing and mode dispatch
- `python/tests/test_ftrace_slice_unit.py`: add tests for `matches`, `find_subtree`, `prune_to_target`; remove `--query` path
- `test-fixtures/tests/test_ftrace_slice.sh`: update E2E to use `--from` instead of `--query`
- `README.md`: update ftrace-slice usage examples

## Verification

1. All existing unit tests pass (existing pure-function tests are unaffected)
2. New unit tests cover: single match, no match, multiple paths, `--to` node strips children, line range narrowing
3. E2E test passes end-to-end: `xtrace | ftrace-slice --from ... | ftrace-expand-refs | ftrace-semantic | ftrace-to-dot`
4. Pipeline stdin/stdout chaining still works
