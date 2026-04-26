# ftrace-slice Decomposition Design

## Goal

Decompose `ftrace-slice` (which currently slices AND expands refs) into two independent, chainable CLI tools following existing pipeline conventions.

## Pipeline

```
xtrace (Java) → ftrace-slice → ftrace-expand-refs → ftrace-semantic → ftrace-to-dot
```

## Tools

### `ftrace-slice`

**Responsibility**: jq-based subtree extraction + ref index bundling.

**CLI**:
```
ftrace-slice --input trace.json --query '<jq expression>' [--output sliced.json]
```

**Behavior**:
1. Run jq with `--query` against `--input` to extract the subtree
2. Walk the full input tree to build a ref index: `{ methodSignature → full node }` — only including signatures that appear as ref nodes in the sliced subtree
3. Output `SlicedTrace` JSON

**Output shape** (`SlicedTrace`):
```json
{
  "slice": { "class": "...", "method": "...", ... },
  "refIndex": {
    "<com.example.Svc: void doWork()>": { ... full node ... }
  }
}
```

The `refIndex` is scoped: only signatures referenced by ref nodes in the slice are included. This keeps the output small.

### `ftrace-expand-refs`

**Responsibility**: Recursive ref replacement with cycle detection.

**CLI**:
```
ftrace-expand-refs --input sliced.json [--output expanded.json]
```

**Behavior**:
1. Read `SlicedTrace` JSON (`{ "slice": ..., "refIndex": ... }`)
2. Recursively replace ref nodes in `slice` using `refIndex`, with cycle detection via path set
3. Output the expanded subtree as a plain trace node (same shape as xtrace output — no wrapper)

Cycle detection: tracks visited `methodSignature` values in a set. If a signature is already in the path, the ref node is returned as-is (not expanded).

`callSiteLine` is preserved from the ref node, not the full expansion.

### stdin/stdout

Both tools follow the existing convention: `--input`/`--output` flags, defaulting to stdin/stdout when omitted. This enables piping:

```bash
uv run ftrace-slice --input trace.json --query '.children[0]' | uv run ftrace-expand-refs --output expanded.json
```

## Types

New in `ftrace_types.py`:

```python
class SlicedTrace(TypedDict):
    slice: dict
    refIndex: dict[str, dict]
```

## Pure Functions

### In `ftrace_slice.py`

- `collect_ref_signatures(node: dict) -> set[str]` — Walk a subtree, return all `methodSignature` values where `ref` is true.
- `index_full_tree(node: dict, signatures: set[str]) -> dict[str, dict]` — Walk the full tree, return `{ sig → node }` for each signature in the given set. First non-ref, non-cycle, non-filtered occurrence wins.

### In `ftrace_expand_refs.py`

- `expand_refs(node: dict, index: dict[str, dict], path: set[str]) -> dict` — Existing function, moved here. Returns a copy with ref nodes replaced.

## Files

| Action | File |
|--------|------|
| Rewrite | `python/ftrace_slice.py` — slice + ref index bundling only |
| Create | `python/ftrace_expand_refs.py` — expand-refs tool |
| Modify | `python/ftrace_types.py` — add `SlicedTrace` |
| Modify | `python/pyproject.toml` — add `ftrace-expand-refs` entry point |
| Rewrite | `python/tests/test_expand_refs.py` — imports from new module |
| Create | `python/tests/test_ftrace_slice_unit.py` — unit tests for slice functions |
| Update | `test-fixtures/tests/test_ftrace_slice.sh` — E2E uses two-tool pipeline |
| Update | `README.md` — pipeline docs, quick reference |

## Testing

- **Unit tests** for `collect_ref_signatures`, `index_full_tree` (scoped), `expand_refs`
- **E2E tests** updated: `test_ftrace_slice.sh` runs `ftrace-slice | ftrace-expand-refs` then pipes through `ftrace-semantic → ftrace-to-dot`
- TDD: tests written before implementation

## Conventions

- FP style: no mutation of inputs, comprehensions over loops, small pure functions
- Strong typing via TypedDict/StrEnum
- No defensive programming (no None/Optional, concrete defaults)
- `--input`/`--output` CLI flags, stdin/stdout defaults
