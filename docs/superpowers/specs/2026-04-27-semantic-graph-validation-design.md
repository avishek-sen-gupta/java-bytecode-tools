# Semantic Graph Validation

## Problem

The semantic graph pipeline (`ftrace-semantic`) can produce structurally invalid graphs — duplicate node IDs, dangling edge references, branch nodes with wrong edge counts, unreachable nodes. These bugs surface as rendering artifacts (edge spaghetti, missing connections) far downstream in the DOT/SVG output, making root cause analysis difficult.

We need a validation step that checks invariants on the finished `MethodSemanticCFG` tree, independent of construction logic.

## Approach

A new module `ftrace_validate.py` containing pure validation functions. It inspects only the output structure of `MethodSemanticCFG` — no knowledge of how the graph was built. Also serves as a UNIX pipeline tool with stdin/stdout semantics.

## Two changes

### 1. Fix branch edge dedup bug

`_build_inter_block_edges` in `ftrace_semantic.py` (lines 504-514) collapses T+F edges into a single unlabeled edge when both point to the same target. This is wrong — branch nodes must always emit both T and F edges. Fix: remove the collapsing logic; allow two edges to the same target when they have different labels.

### 2. Validation module

#### Types

In `ftrace_types.py`:

```python
class ViolationKind(StrEnum):
    DUPLICATE_NODE_ID = "duplicate_node_id"
    DANGLING_EDGE_REF = "dangling_edge_ref"
    DANGLING_CLUSTER_REF = "dangling_cluster_ref"
    INVALID_ENTRY_NODE = "invalid_entry_node"
    BRANCH_EDGE_VIOLATION = "branch_edge_violation"
    NON_BRANCH_EDGE_VIOLATION = "non_branch_edge_violation"
    LEAF_HAS_GRAPH_FIELDS = "leaf_has_graph_fields"
    NO_INCOMING_EDGE = "no_incoming_edge"

class Violation(TypedDict):
    kind: ViolationKind
    node_id: str       # which node, or "" for method-level violations
    method: str        # "Class.method" for context
    message: str       # human-readable description
```

#### Invariants

Each invariant is a small pure function returning `list[Violation]`:

| # | Invariant | Check function | Description |
|---|-----------|----------------|-------------|
| 1 | Unique node IDs | `_check_unique_ids` | No duplicate IDs within a method's `nodes` list |
| 2 | Edge references valid | `_check_edge_refs` | Every `from`/`to` in `edges` references a node ID in this method |
| 3 | Cluster references valid | `_check_cluster_refs` | Every `nodeIds` entry in a cluster references a node that exists |
| 4 | Entry node valid | `_check_entry_node` | `entryNodeId`, if present, references an existing node |
| 5 | Branch node outgoing | `_check_branch_edges` | A `branch` node has exactly 2 outgoing edges: one T, one F |
| 6 | Non-branch node outgoing | `_check_branch_edges` | A non-branch node has at most 1 outgoing edge, never labeled T/F |
| 7 | No T/F from non-branch | `_check_branch_edges` | T/F labels only appear on edges from `branch`-kind nodes |
| 8 | Leaf nodes clean | `_check_leaf_fields` | `ref`/`cycle`/`filtered` nodes have no `nodes`, `edges`, `clusters`, `exceptionEdges` |
| 9 | No unreachable nodes | `_check_reachability` | Every node except `entryNodeId` has at least one incoming edge (from `edges` or `exceptionEdges`) |

#### Public API

```python
def validate_method(method: MethodSemanticCFG) -> list[Violation]:
    """Validate a single method's semantic graph. Does not recurse."""

def validate_tree(root: MethodSemanticCFG) -> list[Violation]:
    """Validate entire tree recursively. Returns all violations."""
```

`validate_method` concatenates results from all check helpers. `validate_tree` recurses into children and collects all violations.

#### Integration with `transform`

`transform` in `ftrace_semantic.py` calls `validate_tree` after `build_semantic_graph_pass`, before returning. It does not act on violations — just returns the graph. The caller decides.

The CLI `ftrace-semantic` logs violations as warnings to stderr after writing output.

#### CLI entry point

`ftrace_validate.py` has a `main()` registered as `ftrace-validate` in `pyproject.toml`.

- `--input`: semantic JSON file (default: stdin)
- `--output`: output file (default: stdout) — pass-through of the input JSON
- Violations printed to stderr as structured text
- Exit code 0 if no violations, 1 if violations found

Pipeline usage:
```bash
ftrace-semantic < trace.json | ftrace-validate | ftrace-to-dot > out.svg
```

Standalone usage:
```bash
ftrace-validate --input semantic.json --output validated.json
```

## Scope

- New file: `ftrace_validate.py`
- New types in `ftrace_types.py`: `ViolationKind`, `Violation`
- New entry point in `pyproject.toml`: `ftrace-validate`
- Fix in `ftrace_semantic.py`: `_build_inter_block_edges` dedup logic
- New test file: `tests/test_validate.py`
- Integration: `transform` calls `validate_tree`, `ftrace-semantic` CLI logs warnings
