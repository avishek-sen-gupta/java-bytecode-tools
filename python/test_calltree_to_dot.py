"""Tests for calltree_to_dot — pure call tree rendering from find-called-methods output."""

from typing import cast

from calltree_to_dot import collect_nodes, collect_edges, make_dot_label, render_dot
from ftrace_types import MethodCFG

# --- Fixtures ---

_ROOT_SIG = "<com.example.Root: void root()>"
_CHILD_A_SIG = "<com.example.A: void doA()>"
_CHILD_B_SIG = "<com.example.B: void doB()>"
_GRANDCHILD_SIG = "<com.example.C: void doC()>"

_ROOT: MethodCFG = cast(
    MethodCFG,
    {
        "class": "com.example.Root",
        "method": "root",
        "methodSignature": _ROOT_SIG,
        "children": [
            {
                "class": "com.example.A",
                "method": "doA",
                "methodSignature": _CHILD_A_SIG,
                "children": [],
            },
            {
                "class": "com.example.B",
                "method": "doB",
                "methodSignature": _CHILD_B_SIG,
                "children": [],
            },
        ],
    },
)

_EMPTY_REF_INDEX: dict[str, MethodCFG] = {}


# --- collect_nodes ---


def test_collect_nodes_simple():
    nodes = collect_nodes(_ROOT, _EMPTY_REF_INDEX)
    assert nodes == frozenset({_ROOT_SIG, _CHILD_A_SIG, _CHILD_B_SIG})


def test_collect_nodes_single_root():
    node: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.Root",
            "method": "root",
            "methodSignature": _ROOT_SIG,
            "children": [],
        },
    )
    assert collect_nodes(node, _EMPTY_REF_INDEX) == frozenset({_ROOT_SIG})


def test_ref_node_resolved_from_ref_index():
    ref_node: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.A",
            "method": "doA",
            "methodSignature": _CHILD_A_SIG,
            "ref": True,
        },
    )
    resolved: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.A",
            "method": "doA",
            "methodSignature": _CHILD_A_SIG,
            "children": [
                {
                    "class": "com.example.C",
                    "method": "doC",
                    "methodSignature": _GRANDCHILD_SIG,
                    "children": [],
                }
            ],
        },
    )
    trace: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.Root",
            "method": "root",
            "methodSignature": _ROOT_SIG,
            "children": [ref_node],
        },
    )
    ref_index: dict[str, MethodCFG] = {_CHILD_A_SIG: resolved}
    nodes = collect_nodes(trace, ref_index)
    assert nodes == frozenset({_ROOT_SIG, _CHILD_A_SIG, _GRANDCHILD_SIG})


def test_cycle_node_included_but_not_expanded():
    cycle_node: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.A",
            "method": "doA",
            "methodSignature": _CHILD_A_SIG,
            "cycle": True,
        },
    )
    trace: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.Root",
            "method": "root",
            "methodSignature": _ROOT_SIG,
            "children": [cycle_node],
        },
    )
    nodes = collect_nodes(trace, _EMPTY_REF_INDEX)
    assert nodes == frozenset({_ROOT_SIG, _CHILD_A_SIG})


def test_no_duplicate_nodes():
    # Same child reachable via two paths
    shared_child: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.A",
            "method": "doA",
            "methodSignature": _CHILD_A_SIG,
            "children": [],
        },
    )
    trace: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.Root",
            "method": "root",
            "methodSignature": _ROOT_SIG,
            "children": [
                {
                    "class": "com.example.B",
                    "method": "doB",
                    "methodSignature": _CHILD_B_SIG,
                    "children": [shared_child],
                },
                shared_child,
            ],
        },
    )
    nodes = collect_nodes(trace, _EMPTY_REF_INDEX)
    assert nodes == frozenset({_ROOT_SIG, _CHILD_B_SIG, _CHILD_A_SIG})
    assert len(nodes) == 3


# --- collect_edges ---


def test_collect_edges_simple():
    edges = collect_edges(_ROOT, _EMPTY_REF_INDEX)
    assert edges == frozenset({(_ROOT_SIG, _CHILD_A_SIG), (_ROOT_SIG, _CHILD_B_SIG)})


def test_no_duplicate_edges():
    # Same edge reachable twice (two ref leaves pointing to same resolved node)
    ref_a1: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.A",
            "method": "doA",
            "methodSignature": _CHILD_A_SIG,
            "ref": True,
        },
    )
    ref_a2: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.A",
            "method": "doA",
            "methodSignature": _CHILD_A_SIG,
            "ref": True,
        },
    )
    trace: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.Root",
            "method": "root",
            "methodSignature": _ROOT_SIG,
            "children": [ref_a1, ref_a2],
        },
    )
    resolved: MethodCFG = cast(
        MethodCFG,
        {
            "class": "com.example.A",
            "method": "doA",
            "methodSignature": _CHILD_A_SIG,
            "children": [],
        },
    )
    ref_index: dict[str, MethodCFG] = {_CHILD_A_SIG: resolved}
    edges = collect_edges(trace, ref_index)
    assert edges == frozenset({(_ROOT_SIG, _CHILD_A_SIG)})


# --- make_dot_label ---


def test_make_dot_label():
    node: MethodCFG = cast(
        MethodCFG, {"class": "com.example.foo.MyClass", "method": "processOrder"}
    )
    assert make_dot_label(node) == "MyClass.processOrder"


# --- render_dot ---


def test_render_dot_contains_nodes_and_edges():
    nodes = frozenset({_ROOT_SIG, _CHILD_A_SIG})
    edges = frozenset({(_ROOT_SIG, _CHILD_A_SIG)})
    label_map = {_ROOT_SIG: "Root.root", _CHILD_A_SIG: "A.doA"}
    dot = render_dot(nodes, edges, label_map)
    assert "digraph" in dot
    assert "->" in dot
    assert "Root.root" in dot
    assert "A.doA" in dot


# --- immutability ---


def test_does_not_mutate_input():
    import copy

    original = copy.deepcopy(_ROOT)
    collect_nodes(_ROOT, _EMPTY_REF_INDEX)
    collect_edges(_ROOT, _EMPTY_REF_INDEX)
    assert _ROOT == original
