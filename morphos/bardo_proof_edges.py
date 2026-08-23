"""BARDO-PROOF-03/v0.2 candidate: proof-carrying transition relations.

The candidate receives the same committed phase facts, public stimuli, claims, and
verification context as the frozen CAUSAL_DAG control. Its only representational
difference is parent composition: a transition edge carries one canonical
commitment to the required parent-edge identity set instead of an explicit list
of parent IDs.
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

_EMPTY_PARENT_COMMITMENT = "sha256:" + hashlib.sha256(
    b"bardo-parent-set:empty"
).hexdigest()


def parent_set_commitment(parent_relation_ids: Sequence[str]) -> str:
    ids = tuple(sorted(parent_relation_ids))
    if not ids:
        return _EMPTY_PARENT_COMMITMENT
    payload = b"bardo-parent-set:" + b"\x00".join(
        item.encode("ascii") for item in ids
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class BardoProofEdge:
    claim: TransitionClaim
    parent_commitment: str

    @property
    def relation_id(self) -> str:
        payload = {
            "claim": asdict(self.claim),
            "parent_commitment": self.parent_commitment,
        }
        return "sha256:" + hashlib.sha256(
            b"bardo-proof-edge:" + _json_bytes(payload)
        ).hexdigest()


@dataclass(frozen=True)
class BardoProof:
    phase_facts: tuple[CommittedPhaseFact, ...]
    stimulus_facts: tuple[tuple[int, int, float], ...]
    edges: tuple[BardoProofEdge, ...]

    def to_jsonable(self) -> dict:
        return {
            "phase_facts": [asdict(fact) for fact in self.phase_facts],
            "stimulus_facts": [list(item) for item in self.stimulus_facts],
            "edges": [
                {
                    "claim": asdict(edge.claim),
                    "parent_commitment": edge.parent_commitment,
                }
                for edge in self.edges
            ],
        }

    def canonical_bytes(self) -> bytes:
        return _json_bytes(self)


def build_bardo_edges(
    claims: Sequence[TransitionClaim], config: Grid2DConfig
) -> tuple[BardoProofEdge, ...]:
    """Build canonical relation edges from claims only; no runtime truth is read."""
    by_tick_site: dict[tuple[int, int], BardoProofEdge] = {}
    built: list[BardoProofEdge] = []
    for claim in claims:
        pre_tick = claim.logical_tick - 1
        parent_ids = []
        for site in (claim.site, *_neighbors(claim.site, config)):
            parent = by_tick_site.get((pre_tick, site))
            if parent is not None:
                parent_ids.append(parent.relation_id)
        edge = BardoProofEdge(claim, parent_set_commitment(parent_ids))
        key = (claim.logical_tick, claim.site)
        if key in by_tick_site:
            raise ValueError("duplicate tick/site claim")
        by_tick_site[key] = edge
        built.append(edge)
    return tuple(built)


def verify_bardo_proof(
    proof: BardoProof, config: Grid2DConfig, context: VerificationContext
) -> bool:
    if len(proof.edges) != len(context.expected_queries):
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

    edges_by_tick_site: dict[tuple[int, int], BardoProofEdge] = {}
    seen_relation_ids: set[str] = set()
    for edge, expected_query in zip(proof.edges, context.expected_queries):
        claim = edge.claim
        key = (claim.logical_tick, claim.site)
        if key != expected_query or key in edges_by_tick_site:
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

        required_parent_ids: list[str] = []
        for site in (claim.site, *neighbor_sites):
            parent = edges_by_tick_site.get((pre_tick, site))
            if parent is not None:
                disclosed = fact_map.get((pre_tick, site))
                if disclosed is None or parent.claim.phase_after != disclosed.phase:
                    return False
                required_parent_ids.append(parent.relation_id)

        if edge.parent_commitment != parent_set_commitment(required_parent_ids):
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

        relation_id = edge.relation_id
        if relation_id in seen_relation_ids:
            return False
        seen_relation_ids.add(relation_id)
        edges_by_tick_site[key] = edge

    return True


def bardo_proof_metrics(proof: BardoProof, config: Grid2DConfig) -> dict:
    paths = sum(len(fact.auth_path) for fact in proof.phase_facts)
    parent_commitments = sum(
        edge.parent_commitment != _EMPTY_PARENT_COMMITMENT for edge in proof.edges
    )
    return {
        "canonical_proof_payload_bytes": len(proof.canonical_bytes()),
        "unique_phase_facts_disclosed": len(proof.phase_facts),
        "merkle_sibling_hashes_disclosed": paths,
        "unique_stimulus_facts_disclosed": len(proof.stimulus_facts),
        "parent_references_disclosed": parent_commitments,
        "local_transition_evaluations": len(proof.edges),
        # Same phase-fact/Merkle work as CAUSAL_DAG, one relation-id hash per
        # edge, and one parent-set hash only when parents exist.
        "hash_evaluations": (
            len(proof.phase_facts)
            + paths
            + len(proof.edges)
            + parent_commitments
        ),
        "proof_objects_traversed": (
            len(proof.phase_facts) + len(proof.stimulus_facts) + len(proof.edges)
        ),
    }
