# Design: Rewrite merge_source_trace with reduce

**Date:** 2026-04-27
**Issue:** java-bytecode-tools-8k8
**File:** `python/ftrace_semantic.py:119-133`

## Context

`merge_source_trace` uses an imperative `for` loop with dictionary mutations and `.append()`. Its sibling `merge_block_stmts` (line 113) already uses `reduce()` with a pure accumulator `_accumulate_stmt`. This inconsistency violates the project's FP style. The fix: mirror the existing pattern.

## Design

### New function: `_accumulate_source_trace`

```python
def _accumulate_source_trace(
    acc: dict[int, MergedStmt], entry: SourceTraceEntry
) -> dict[int, MergedStmt]:
    """Fold a single source trace entry into the accumulator, keyed by line number."""
    line = entry["line"]
    if line < 0:
        return acc
    existing = acc.get(line, {"line": line, "calls": [], "branches": [], "assigns": []})
    new_calls = [c for c in entry.get("calls", []) if c not in existing["calls"]]
    return {
        **acc,
        line: {
            **existing,
            "calls": existing["calls"] + new_calls,
            "branches": existing["branches"] + ([entry["branch"]] if "branch" in entry else []),
        },
    }
```

### Rewritten `merge_source_trace`

```python
def merge_source_trace(source_trace: list[SourceTraceEntry]) -> list[MergedStmt]:
    """Deduplicate sourceTrace by line number, merging calls and branches."""
    by_line = reduce(_accumulate_source_trace, source_trace, {})
    return [by_line[ln] for ln in sorted(by_line)]
```

## Behavioral notes

- Call deduplication preserved (matches current behavior)
- Branch appending without dedup preserved
- `assigns` stays `[]` (no assign field in SourceTraceEntry)
- Negative lines filtered (guard clause in accumulator)

## Testing

- All 4 existing `TestMergeSourceTrace` tests cover the behavior
- Add 1 immutability test: `test_does_not_mutate_input`
- Add 1 unit test for `_accumulate_source_trace` directly (empty acc, negative line)
- Run full suite: `cd python && uv run pytest`

## Verification

```bash
cd python && uv run pytest tests/test_merge_stmts.py -v
cd python && uv run pytest
```
