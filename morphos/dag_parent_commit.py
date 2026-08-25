"""Generic parent-set committed DAG control for BARDO-PROOF-04.

This control deliberately receives the same authenticated facts, public stimuli,
claims, and parent-set compression opportunity as the frozen Bardo proof edge.
It uses ordinary DAG terminology and no Bardo-specific runtime or authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Sequence

from morphos.grid2d import Grid2DConfig
from morphos.proof_controls_v02 import (
    CommittedPhaseFact,
    TransitionClaim,
    VerificationContext,
    _json_bytes,
    _neighbors,
    _verify_local_fact,
    evaluate_local_transition,
)


def parent_set_commitment(parent_node_ids: Sequence[str]) -> str | None:
    ids = tuple(sorted(parent_node_ids))
    if not ids:
        return None
    payload = b"dag-parent-set:" + b"\x00".join(item.encode("ascii") for item in ids)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class DagCommitNode:
    claim: TransitionClaim
    parent_commitment: str | None

    @property
    def node_id(self) -> str:
        payload = {
            "claim": asdict(self.claim),
            "parent_commitment": self.parent_commitment,
        }
        return "sha256:" + hashlib.sha256(
            b"dag-commit-node:" + _json_bytes(payload)
        ).hexdigest()


@dataclass(frozen=True)
class DagParentCommitProof:
    phase_facts: tuple[CommittedPhaseFact, ...]
    stimulus_facts: tuple[tuple[int, int, float], ...]
    nodes: tuple[DagCommitNode, ...]

    def to_jsonable(self) -> dict:
        return {
            "phase_facts": [asdict(fact) for fact in self.phase_facts],
            "stimulus_facts": [list(item) for item in self.stimulus_facts],
            "nodes": [
                {
                    "claim": asdict(node.claim),
                    "parent_commitment": node.parent_commitment,
                }
                for node in self.nodes
            ],
        }

    def canonical_bytes(self) -> bytes:
        return _json_bytes(self)


def build_dag_nodes(
    claims: Sequence[TransitionClaim], config: Grid2DConfig
) -> tuple[DagCommitNode, ...]:
    by_tick_site: dict[tuple[int, int], DagCommitNode] = {}
    nodes: list[DagCommitNode] = []
    for claim in claims:
        pre_tick = claim.logical_tick - 1
        parent_ids = []
        for site in (claim.site, *_neighbors(claim.site, config)):
            parent = by_tick_site.get((pre_tick, site))
            if parent is not None:
                parent_ids.append(parent.node_id)
        node = DagCommitNode(claim, parent_set_commitment(parent_ids))
        key = (claim.logical_tick, claim.site)
        if key in by_tick_site:
            raise ValueError("duplicate tick/site claim")
        by_tick_site[key] = node
        nodes.append(node)
    return tuple(nodes)


def verify_dag_parent_commit(
    proof: DagParentCommitProof,
    config: Grid2DConfig,
    context: VerificationContext,
) -> bool:
    if len(proof.nodes) != len(context.expected_queries):
        return False

    fact_map: dict[tuple[int, int], CommittedPhaseFact] = {}
    for fact in proof.phase_facts:
        key = (fact.tick, fact.site)
        if key in fact_map and fact_map[key] != fact:
            return False
        if not _verify_local_fact(fact, fact.tick, fact.site, context):
            return False
        fact_map[key] = fact

    stimulus_map: dict[tuple[int, int], float] = {}
    for tick, site, value in proof.stimulus_facts:
        key = (tick, site)
        if key in stimulus_map and stimulus_map[key] != float(value):
            return False
        expected = context.stimulus_at(tick, site)
        if expected is None or expected != float(value):
            return False
        stimulus_map[key] = float(value)

    nodes_by_tick_site: dict[tuple[int, int], DagCommitNode] = {}
    seen_ids: set[str] = set()
    for node, expected_query in zip(proof.nodes, context.expected_queries):
        claim = node.claim
        key = (claim.logical_tick, claim.site)
        if key != expected_query or key in nodes_by_tick_site:
            return False

        pre_tick = claim.logical_tick - 1
        own = fact_map.get((pre_tick, claim.site))
        stimulus = stimulus_map.get(key)
        if own is None or stimulus is None:
            return False
        neighbor_sites = _neighbors(claim.site, config)
        neighbors = [fact_map.get((pre_tick, site)) for site in neighbor_sites]
        if any(fact is None for fact in neighbors):
            return False

        required_parent_ids = []
        for site in (claim.site, *neighbor_sites):
            parent = nodes_by_tick_site.get((pre_tick, site))
            if parent is not None:
                disclosed = fact_map.get((pre_tick, site))
                if disclosed is None or parent.claim.phase_after != disclosed.phase:
                    return False
                required_parent_ids.append(parent.node_id)
        if node.parent_commitment != parent_set_commitment(required_parent_ids):
            return False

        try:
            expected_after = evaluate_local_transition(
                site=claim.site,
                phase_before=own.phase,
                neighbor_phases=[fact.phase for fact in neighbors if fact is not None],
                stimulus=stimulus,
                config=config,
            )
        except ValueError:
            return False
        if expected_after != claim.phase_after:
            return False

        node_id = node.node_id
        if node_id in seen_ids:
            return False
        seen_ids.add(node_id)
        nodes_by_tick_site[key] = node

    return True


def dag_parent_commit_metrics(proof: DagParentCommitProof, config: Grid2DConfig) -> dict:
    paths = sum(len(fact.auth_path) for fact in proof.phase_facts)
    parent_commitments = sum(node.parent_commitment is not None for node in proof.nodes)
    return {
        "canonical_proof_payload_bytes": len(proof.canonical_bytes()),
        "unique_phase_facts_disclosed": len(proof.phase_facts),
        "merkle_sibling_hashes_disclosed": paths,
        "unique_stimulus_facts_disclosed": len(proof.stimulus_facts),
        "parent_references_disclosed": parent_commitments,
        "local_transition_evaluations": len(proof.nodes),
        "hash_evaluations": len(proof.phase_facts) + paths + len(proof.nodes) + parent_commitments,
        "proof_objects_traversed": len(proof.phase_facts) + len(proof.stimulus_facts) + len(proof.nodes),
    }
