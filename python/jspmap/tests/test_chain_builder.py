"""Tests for chain_builder BFS tracer."""

import copy
import re

from jspmap.chain_builder import ChainHop, build_chains

# Helpers — all sigs follow the Soot format <FQCN: returnType method(args)>
DAO_PAT = re.compile(r"com\.example\.dao")
NO_LAYERS: dict[str, re.Pattern] = {}


def _sig(fqcn: str, method: str) -> str:
    return f"<{fqcn}: void {method}()>"


class TestBuildChainsBasic:
    def test_single_hop_entry_is_dao(self):
        # Entry point IS the DAO — one chain of length 1
        cg = {_sig("com.example.dao.Dao", "save"): []}
        chains = build_chains(
            cg, _sig("com.example.dao.Dao", "save"), DAO_PAT, NO_LAYERS
        )
        assert len(chains) == 1
        assert chains[0][0].fqcn == "com.example.dao.Dao"

    def test_multi_hop_chain(self):
        entry = _sig("com.example.web.Action", "submit")
        service = _sig("com.example.svc.Service", "process")
        dao = _sig("com.example.dao.Dao", "save")
        cg = {entry: [service], service: [dao], dao: []}
        chains = build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert len(chains) == 1
        assert [h.method for h in chains[0]] == ["submit", "process", "save"]

    def test_no_dao_reached_returns_empty(self):
        entry = _sig("com.example.web.Action", "submit")
        service = _sig("com.example.svc.Service", "process")
        cg = {entry: [service], service: []}
        chains = build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert chains == []

    def test_cycle_detected_no_chain(self):
        entry = _sig("com.example.web.Action", "a")
        b = _sig("com.example.web.Action", "b")
        cg = {entry: [b], b: [entry]}  # cycle
        chains = build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert chains == []

    def test_multiple_chains_to_different_daos(self):
        entry = _sig("com.example.web.Action", "submit")
        dao1 = _sig("com.example.dao.Dao1", "save")
        dao2 = _sig("com.example.dao.Dao2", "find")
        cg = {entry: [dao1, dao2], dao1: [], dao2: []}
        chains = build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert len(chains) == 2
        leaf_methods = {chains[0][-1].method, chains[1][-1].method}
        assert leaf_methods == {"save", "find"}

    def test_max_depth_respected(self):
        # Linear chain longer than max_depth — no chain reaches dao
        sigs = [_sig(f"com.example.svc.S{i}", "m") for i in range(10)]
        dao = _sig("com.example.dao.Dao", "save")
        cg = {sigs[i]: [sigs[i + 1]] for i in range(9)}
        cg[sigs[9]] = [dao]
        cg[dao] = []
        # max_depth=5 means we stop before reaching the dao
        chains = build_chains(cg, sigs[0], DAO_PAT, NO_LAYERS, max_depth=5)
        assert chains == []

    def test_does_not_mutate_call_graph(self):
        entry = _sig("com.example.web.Action", "submit")
        dao = _sig("com.example.dao.Dao", "save")
        cg = {entry: [dao], dao: []}
        original = copy.deepcopy(cg)
        build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert cg == original


class TestBuildChainsLayerAnnotation:
    def test_layer_assigned_to_hops(self):
        entry = _sig("com.example.web.Action", "submit")
        dao = _sig("com.example.dao.Dao", "save")
        cg = {entry: [dao], dao: []}
        layers = {
            "web": re.compile(r"com\.example\.web"),
            "dao": re.compile(r"com\.example\.dao"),
        }
        chains = build_chains(cg, entry, DAO_PAT, layers)
        assert chains[0][0].layer == "web"
        assert chains[0][1].layer == "dao"

    def test_no_matching_layer_gives_empty_string(self):
        entry = _sig("com.example.web.Action", "submit")
        dao = _sig("com.example.dao.Dao", "save")
        cg = {entry: [dao], dao: []}
        # Layer pattern does not match anything
        layers = {"other": re.compile(r"com\.other")}
        chains = build_chains(cg, entry, DAO_PAT, layers)
        assert chains[0][0].layer == ""


class TestChainHopFields:
    def test_hop_fqcn_extracted_correctly(self):
        entry = _sig("com.example.web.Action", "submit")
        dao = _sig("com.example.dao.Dao", "save")
        cg = {entry: [dao], dao: []}
        chains = build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert chains[0][0].fqcn == "com.example.web.Action"
        assert chains[0][0].method == "submit"
        assert chains[0][0].signature == entry
