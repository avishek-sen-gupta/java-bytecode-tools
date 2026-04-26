"""Tests for pass 2: assign_clusters."""

from ftrace_types import ClusterAssignment, ClusterRole


class TestAssignTrapClusters:
    """Unit tests for the cluster assignment function."""

    def test_handler_wins_over_coverage(self):
        from ftrace_semantic import assign_trap_clusters

        traps = [
            {
                "type": "java.lang.Throwable",
                "handler": "B3",
                "coveredBlocks": ["B0", "B1", "B3"],
                "handlerBlocks": ["B3", "B4"],
            },
        ]
        result = assign_trap_clusters(traps)
        assert result["B3"] == {"kind": ClusterRole.HANDLER, "trapIndex": 0}
        assert result["B0"] == {"kind": ClusterRole.TRY, "trapIndex": 0}

    def test_handler_blocks_excluded_from_coverage(self):
        from ftrace_semantic import assign_trap_clusters

        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B5",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B5", "B6"],
            },
            {
                "type": "java.lang.Throwable",
                "handler": "B7",
                "coveredBlocks": ["B0", "B1", "B5", "B6"],
                "handlerBlocks": ["B7"],
            },
        ]
        result = assign_trap_clusters(traps)
        # B5 is handler for trap 0, should not be covered by trap 1
        assert result["B5"] == {"kind": ClusterRole.HANDLER, "trapIndex": 0}
        assert result["B6"] == {"kind": ClusterRole.HANDLER, "trapIndex": 0}

    def test_empty_traps(self):
        from ftrace_semantic import assign_trap_clusters

        assert assign_trap_clusters([]) == {}

    def test_no_overlap(self):
        from ftrace_semantic import assign_trap_clusters

        traps = [
            {
                "type": "java.lang.Exception",
                "handler": "B3",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B3"],
            },
        ]
        result = assign_trap_clusters(traps)
        assert result["B0"] == {"kind": ClusterRole.TRY, "trapIndex": 0}
        assert result["B1"] == {"kind": ClusterRole.TRY, "trapIndex": 0}
        assert result["B3"] == {"kind": ClusterRole.HANDLER, "trapIndex": 0}

    def test_first_trap_wins_for_coverage(self):
        from ftrace_semantic import assign_trap_clusters

        traps = [
            {
                "type": "java.lang.RuntimeException",
                "handler": "B5",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B5"],
            },
            {
                "type": "java.lang.Throwable",
                "handler": "B6",
                "coveredBlocks": ["B0", "B1"],
                "handlerBlocks": ["B6"],
            },
        ]
        result = assign_trap_clusters(traps)
        assert result["B0"] == {"kind": ClusterRole.TRY, "trapIndex": 0}


class TestBlocksForCluster:
    def test_returns_matching_blocks(self):
        from ftrace_semantic import blocks_for_cluster

        assignment = {
            "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B1": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
        }
        assert blocks_for_cluster(assignment, "try", 0) == ["B0", "B1"]
        assert blocks_for_cluster(assignment, "handler", 0) == ["B3"]

    def test_empty_assignment(self):
        from ftrace_semantic import blocks_for_cluster

        assert blocks_for_cluster({}, "try", 0) == []


class TestAssignClustersPass:
    def test_adds_cluster_assignment_to_method_node(self):
        from ftrace_semantic import assign_clusters_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [
                {"id": "B0", "stmts": [{"line": 5}], "successors": []},
            ],
            "traps": [
                {
                    "type": "java.lang.Exception",
                    "handler": "B1",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B1"],
                },
            ],
            "children": [],
        }
        result = assign_clusters_pass(tree)
        assert "clusterAssignment" in result
        assert result["clusterAssignment"]["B0"] == {
            "kind": ClusterRole.TRY,
            "trapIndex": 0,
        }

    def test_leaf_node_passes_through(self):
        from ftrace_semantic import assign_clusters_pass

        tree = {"class": "Svc", "method": "run", "ref": True, "methodSignature": "sig"}
        result = assign_clusters_pass(tree)
        assert "clusterAssignment" not in result

    def test_no_traps_empty_assignment(self):
        from ftrace_semantic import assign_clusters_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0", "stmts": [{"line": 5}], "successors": []}],
            "traps": [],
            "children": [],
        }
        result = assign_clusters_pass(tree)
        assert result["clusterAssignment"] == {}

    def test_does_not_mutate_input(self):
        from ftrace_semantic import assign_clusters_pass
        import copy

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [{"id": "B0", "stmts": [{"line": 5}], "successors": []}],
            "traps": [
                {
                    "type": "java.lang.Exception",
                    "handler": "B1",
                    "coveredBlocks": ["B0"],
                    "handlerBlocks": ["B1"],
                },
            ],
            "children": [],
        }
        original = copy.deepcopy(tree)
        assign_clusters_pass(tree)
        assert tree == original
