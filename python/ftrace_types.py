"""Shared type definitions for the ftrace pipeline.

All structured data flowing between pipeline stages is typed here.
Uses TypedDict for JSON-compatible structures, StrEnum for constrained fields.
"""

from enum import StrEnum
from typing import TypedDict


class NodeKind(StrEnum):
    """Kinds of semantic graph nodes."""

    PLAIN = "plain"
    CALL = "call"
    BRANCH = "branch"
    ASSIGN = "assign"
    CYCLE = "cycle"
    REF = "ref"
    FILTERED = "filtered"


class ClusterRole(StrEnum):
    """Role of a cluster in exception handling."""

    TRY = "try"
    HANDLER = "handler"


class BranchLabel(StrEnum):
    """Label for edges from branch nodes."""

    T = "T"
    F = "F"


# RawStmt: line is required, rest are optional
class _RawStmtRequired(TypedDict):
    line: int


class RawStmt(_RawStmtRequired, total=False):
    """Statement in original bytecode.

    Fields:
    - line: bytecode line number (required)
    - call: method called, if any
    - branch: branch condition, if any
    - assign: variable assigned, if any
    """

    call: str
    branch: str
    assign: str


class MergedStmt(TypedDict):
    """Statement after merging consecutive raw statements.

    All fields required.
    """

    line: int
    calls: list[str]
    branches: list[str]
    assigns: list[str]


# SourceTraceEntry: line required, calls/branch optional
class _SourceTraceEntryRequired(TypedDict):
    line: int


class SourceTraceEntry(_SourceTraceEntryRequired, total=False):
    """Entry in a source trace.

    Fields:
    - line: source line number (required)
    - calls: methods called on this line (optional)
    - branch: branch condition, if any (optional)
    """

    calls: list[str]
    branch: str


# RawBlockEdge: fromBlock, toBlock required; label optional
_RawBlockEdgeRequired = TypedDict(
    "_RawBlockEdgeRequired",
    {
        "fromBlock": str,
        "toBlock": str,
    },
)


class RawBlockEdge(_RawBlockEdgeRequired, total=False):
    """Edge between two blocks in the control flow graph.

    Fields:
    - fromBlock: source block ID (required)
    - toBlock: target block ID (required)
    - label: "T" or "F" for branch edges (optional, absent for unconditional)
    """

    label: str


# RawBlock: id, stmts required
class _RawBlockRequired(TypedDict):
    id: str
    stmts: list[RawStmt]


class RawBlock(_RawBlockRequired, total=False):
    """Block of bytecode instructions.

    Fields:
    - id: block identifier (required)
    - stmts: statements in block (required)
    - branchCondition: condition if this is a branch block
    - mergedStmts: merged statements (replaces stmts in pass 1)
    """

    branchCondition: str
    mergedStmts: list[MergedStmt]


class RawTrap(TypedDict):
    """Exception trap from xtrace output.

    All fields required.
    """

    handler: str
    type: str
    coveredBlocks: list[str]
    handlerBlocks: list[str]


class ClusterAssignment(TypedDict):
    """Assignment of a block to a cluster role.

    All fields required.
    """

    kind: ClusterRole
    trapIndex: int


# BlockAliases is just a type alias for dict[str, str]
# representing alias -> canonical block ID mappings
BlockAliases = dict[str, str]


class SemanticNode(TypedDict):
    """Node in the semantic graph.

    All fields required.
    """

    id: str
    lines: list[int]
    kind: NodeKind
    label: list[str]


# SemanticEdge: from/to required, branch optional
# Use functional syntax with base class to make from/to required
_SemanticEdgeBase = TypedDict(
    "_SemanticEdgeBase",
    {
        "from": str,
        "to": str,
    },
)


class SemanticEdge(_SemanticEdgeBase, total=False):
    """Edge in the semantic graph.

    Fields (accessed via string keys due to 'from' being a reserved word):
    - from: source node ID (required)
    - to: target node ID (required)
    - branch: branch label if from a conditional (optional)
    """

    branch: str


# SemanticCluster: trapType, role, nodeIds required; entryNodeId optional
class _SemanticClusterRequired(TypedDict):
    trapType: str
    role: ClusterRole
    nodeIds: list[str]


class SemanticCluster(_SemanticClusterRequired, total=False):
    """Cluster of nodes representing an exception-handling region.

    Fields:
    - trapType: exception type handled (required)
    - role: TRY or HANDLER (required)
    - nodeIds: nodes in cluster (required)
    - entryNodeId: entry node if cluster is a handler (optional)
    """

    entryNodeId: str


# ExceptionEdge: all fields required
# Use functional syntax to handle 'from' keyword
ExceptionEdge = TypedDict(
    "ExceptionEdge",
    {
        "from": str,
        "to": str,
        "trapType": str,
        "fromCluster": int,
        "toCluster": int,
    },
)


# Use functional syntax for base because "class" is a reserved keyword
_MethodCFGRequired = TypedDict("_MethodCFGRequired", {"class": str}, total=False)


class MethodCFG(_MethodCFGRequired, total=False):
    """Recursive trace node representing a method in the call tree.

    Shape changes through pipeline stages (passes 1-3). All fields optional
    because leaf nodes (ref/cycle/filtered) carry only a subset.

    Pass 4 (build_semantic_graph) consumes this type and produces
    MethodSemanticCFG. Semantic graph fields live there, not here.

    Raw fields (from xtrace):
    - class, method, methodSignature: method identity
    - blocks, traps, sourceTrace: raw bytecode data
    - children: recursive child method calls
    - ref, cycle, filtered: leaf-node markers
    - callSiteLine: line where this method was called

    Enriched fields (added by pipeline passes 1-3):
    - mergedSourceTrace, clusterAssignment, blockAliases: intermediate
    """

    # Method identity
    method: str
    methodSignature: str

    # Raw fields (from xtrace)
    blocks: list[RawBlock]
    edges: list[RawBlockEdge]
    traps: list[RawTrap]
    sourceTrace: list[SourceTraceEntry]
    children: list["MethodCFG"]

    # Leaf markers
    ref: bool
    cycle: bool
    filtered: bool
    callSiteLine: int

    # Pass 1: merge_stmts
    mergedSourceTrace: list[MergedStmt]

    # Pass 2: assign_clusters
    clusterAssignment: dict[str, ClusterAssignment]

    # Pass 3: deduplicate_blocks
    blockAliases: BlockAliases


# Use functional syntax for base because "class" is a reserved keyword
_MethodSemanticCFGRequired = TypedDict(
    "_MethodSemanticCFGRequired", {"class": str}, total=False
)


class MethodSemanticCFG(_MethodSemanticCFGRequired, total=False):
    """Semantic graph representation of a method in the call tree.

    Produced by pass 4 (build_semantic_graph). Contains only identity,
    leaf markers, semantic graph fields, and recursive children.
    No raw or intermediate pipeline fields.
    """

    # Identity
    method: str
    methodSignature: str

    # Leaf markers
    ref: bool
    cycle: bool
    filtered: bool
    callSiteLine: int

    # Semantic graph (intra-method)
    nodes: list[SemanticNode]
    edges: list[SemanticEdge]
    clusters: list[SemanticCluster]
    exceptionEdges: list[ExceptionEdge]
    entryNodeId: str

    # Inter-method (recursive)
    children: list["MethodSemanticCFG"]


class SlicedTrace(TypedDict):
    """Output of ftrace-slice: a sliced subtree plus a ref index for expansion.

    Fields:
    - slice: the sliced subtree (trace node)
    - refIndex: methodSignature -> full node, scoped to refs in the slice
    """

    slice: MethodCFG
    refIndex: dict[str, MethodCFG]
