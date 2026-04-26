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


# RawBlock: id, stmts, successors are required
class _RawBlockRequired(TypedDict):
    id: str
    stmts: list[RawStmt]
    successors: list[str]


class RawBlock(_RawBlockRequired, total=False):
    """Block of bytecode instructions.

    Fields:
    - id: block identifier (required)
    - stmts: statements in block (required)
    - successors: successor block IDs (required)
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
