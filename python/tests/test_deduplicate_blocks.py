"""Tests for pass 3: deduplicate_blocks."""

from ftrace_types import ClusterRole


class TestBlockContentSignature:
    def test_same_content_same_sig(self):
        from ftrace_semantic import block_content_signature

        b1 = {
            "id": "B3",
            "mergedStmts": [
                {
                    "line": 14,
                    "calls": ["PrintStream.println"],
                    "branches": [],
                    "assigns": [],
                }
            ],
            "stmts": [],
        }
        b2 = {
            "id": "B8",
            "mergedStmts": [
                {
                    "line": 14,
                    "calls": ["PrintStream.println"],
                    "branches": [],
                    "assigns": [],
                }
            ],
            "stmts": [],
        }
        assert block_content_signature(b1) == block_content_signature(b2)

    def test_different_content_different_sig(self):
        from ftrace_semantic import block_content_signature

        b1 = {
            "id": "B3",
            "mergedStmts": [
                {
                    "line": 14,
                    "calls": ["PrintStream.println"],
                    "branches": [],
                    "assigns": [],
                }
            ],
            "stmts": [],
        }
        b2 = {
            "id": "B4",
            "mergedStmts": [{"line": 15, "calls": [], "branches": [], "assigns": []}],
            "stmts": [],
        }
        assert block_content_signature(b1) != block_content_signature(b2)

    def test_branch_condition_included(self):
        from ftrace_semantic import block_content_signature

        b1 = {
            "id": "B0",
            "mergedStmts": [
                {"line": 6, "calls": [], "branches": ["i <= 0"], "assigns": []}
            ],
            "branchCondition": "i <= 0",
            "stmts": [],
        }
        b2 = {
            "id": "B1",
            "mergedStmts": [
                {"line": 6, "calls": [], "branches": ["i <= 0"], "assigns": []}
            ],
            "stmts": [],
        }
        assert block_content_signature(b1) != block_content_signature(b2)

    def test_empty_merged_stmts(self):
        from ftrace_semantic import block_content_signature

        b = {"id": "B0", "mergedStmts": [], "stmts": []}
        sig = block_content_signature(b)
        assert isinstance(sig, str)


class TestComputeBlockAliases:
    def test_duplicates_within_same_cluster(self):
        from ftrace_semantic import compute_block_aliases

        blocks = [
            {
                "id": "B3",
                "mergedStmts": [
                    {
                        "line": 14,
                        "calls": ["PrintStream.println"],
                        "branches": [],
                        "assigns": [],
                    }
                ],
                "stmts": [],
            },
            {
                "id": "B8",
                "mergedStmts": [
                    {
                        "line": 14,
                        "calls": ["PrintStream.println"],
                        "branches": [],
                        "assigns": [],
                    }
                ],
                "stmts": [],
            },
        ]
        cluster_assignment = {
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            "B8": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
        }
        aliases = compute_block_aliases(blocks, cluster_assignment)
        assert aliases == {"B8": "B3"}

    def test_no_duplicates(self):
        from ftrace_semantic import compute_block_aliases

        blocks = [
            {
                "id": "B0",
                "mergedStmts": [
                    {"line": 5, "calls": [], "branches": [], "assigns": []}
                ],
                "stmts": [],
            },
            {
                "id": "B1",
                "mergedStmts": [
                    {"line": 10, "calls": [], "branches": [], "assigns": []}
                ],
                "stmts": [],
            },
        ]
        cluster_assignment = {
            "B0": {"kind": ClusterRole.TRY, "trapIndex": 0},
            "B1": {"kind": ClusterRole.TRY, "trapIndex": 0},
        }
        aliases = compute_block_aliases(blocks, cluster_assignment)
        assert aliases == {}

    def test_different_clusters_not_aliased(self):
        from ftrace_semantic import compute_block_aliases

        blocks = [
            {
                "id": "B3",
                "mergedStmts": [
                    {
                        "line": 14,
                        "calls": ["PrintStream.println"],
                        "branches": [],
                        "assigns": [],
                    }
                ],
                "stmts": [],
            },
            {
                "id": "B8",
                "mergedStmts": [
                    {
                        "line": 14,
                        "calls": ["PrintStream.println"],
                        "branches": [],
                        "assigns": [],
                    }
                ],
                "stmts": [],
            },
        ]
        cluster_assignment = {
            "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
            "B8": {"kind": ClusterRole.HANDLER, "trapIndex": 1},
        }
        aliases = compute_block_aliases(blocks, cluster_assignment)
        assert aliases == {}

    def test_unassigned_blocks_not_aliased(self):
        from ftrace_semantic import compute_block_aliases

        blocks = [
            {
                "id": "B0",
                "mergedStmts": [
                    {"line": 5, "calls": [], "branches": [], "assigns": []}
                ],
                "stmts": [],
            },
            {
                "id": "B1",
                "mergedStmts": [
                    {"line": 5, "calls": [], "branches": [], "assigns": []}
                ],
                "stmts": [],
            },
        ]
        aliases = compute_block_aliases(blocks, {})
        assert aliases == {}


class TestDeduplicateBlocksPass:
    def test_adds_block_aliases(self):
        from ftrace_semantic import deduplicate_blocks_pass

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [
                {
                    "id": "B3",
                    "mergedStmts": [
                        {
                            "line": 14,
                            "calls": ["PrintStream.println"],
                            "branches": [],
                            "assigns": [],
                        }
                    ],
                    "stmts": [],
                },
                {
                    "id": "B8",
                    "mergedStmts": [
                        {
                            "line": 14,
                            "calls": ["PrintStream.println"],
                            "branches": [],
                            "assigns": [],
                        }
                    ],
                    "stmts": [],
                },
            ],
            "traps": [],
            "metadata": {
                "clusterAssignment": {
                    "B3": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
                    "B8": {"kind": ClusterRole.HANDLER, "trapIndex": 0},
                },
            },
            "children": [],
        }
        result = deduplicate_blocks_pass(tree)
        assert result["metadata"]["blockAliases"] == {"B8": "B3"}

    def test_leaf_node_passes_through(self):
        from ftrace_semantic import deduplicate_blocks_pass

        tree = {"class": "Svc", "method": "run", "ref": True, "methodSignature": "sig"}
        result = deduplicate_blocks_pass(tree)
        assert "blockAliases" not in result.get("metadata", {})

    def test_does_not_mutate_input(self):
        from ftrace_semantic import deduplicate_blocks_pass
        import copy

        tree = {
            "class": "Svc",
            "method": "run",
            "blocks": [
                {
                    "id": "B0",
                    "mergedStmts": [
                        {"line": 5, "calls": [], "branches": [], "assigns": []}
                    ],
                    "stmts": [],
                },
            ],
            "traps": [],
            "metadata": {"clusterAssignment": {}},
            "children": [],
        }
        original = copy.deepcopy(tree)
        deduplicate_blocks_pass(tree)
        assert tree == original
