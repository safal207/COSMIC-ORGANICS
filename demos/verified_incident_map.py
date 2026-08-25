"""Verified incident-map demo for the frozen COSMIC-KERNEL-05 surface.

Application mapping (software model only):

- A = nominal
- M = elevated / transition
- C = critical

Two localized incident clusters are raised and later remediated on a 16x16
service map. The exact same workload is executed by a dense reference and the
strong conventional dirty-frontier scheduler. Every completed transition is
audited by the same Merkle-bound generic causal-proof mechanism.

This is an application/reproducibility demo, not a new benchmark claim and not
an assertion that A/M/C are calibrated physical or operational risk states.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from typing import Iterable, Sequence

from morphos.cosmic_kernel import CommittedProofKernel
from morphos.dag_parent_commit import verify_dag_parent_commit
from morphos.grid2d import Grid2DConfig
from morphos.sparse_scheduler import DirtyNodeGrid2D, InstrumentedDenseGrid2D

WIDTH = 16
HEIGHT = 16
CELLS = WIDTH * HEIGHT
PROOF_SEED = 2026082501

PRIMARY_INCIDENT = (
    (7, 6),
    (7, 7),
    (7, 8),
    (8, 7),
    (8, 8),
    (8, 9),
)
SECONDARY_INCIDENT = (
    (3, 12),
    (3, 13),
    (4, 12),
    (4, 13),
)


def _site(row: int, col: int) -> int:
    if not (0 <= row < HEIGHT and 0 <= col < WIDTH):
        raise ValueError("incident coordinate outside the demo map")
    return row * WIDTH + col


def _vector(assignments: Iterable[tuple[Sequence[tuple[int, int]], float]]) -> list[float]:
    values = [0.0] * CELLS
    for coordinates, value in assignments:
        for row, col in coordinates:
            values[_site(row, col)] = float(value)
    return values


def incident_schedule() -> tuple[list[float], ...]:
    """Return a deterministic 24-tick incident/remediation schedule."""
    schedule: list[list[float]] = []
    for tick in range(24):
        assignments: list[tuple[Sequence[tuple[int, int]], float]] = []

        if 1 <= tick <= 3:
            assignments.append((PRIMARY_INCIDENT, 0.90))
        if 8 <= tick <= 10:
            assignments.append((SECONDARY_INCIDENT, 0.90))
        if 12 <= tick <= 14:
            assignments.append((PRIMARY_INCIDENT, -0.90))
        if 17 <= tick <= 19:
            assignments.append((SECONDARY_INCIDENT, -0.90))

        schedule.append(_vector(assignments))
    return tuple(schedule)


def _phase_counts(state: str) -> dict[str, int]:
    return {phase: state.count(phase) for phase in "AMC"}


def _mutated_proof_is_rejected(kernel: CommittedProofKernel) -> bool:
    proof = kernel.proof()
    if not proof.nodes:
        raise RuntimeError("demo generated no audited transitions")
    first = proof.nodes[0]
    wrong_phase = next(phase for phase in "AMC" if phase != first.claim.phase_after)
    mutated_node = replace(first, claim=replace(first.claim, phase_after=wrong_phase))
    mutated = replace(proof, nodes=(mutated_node, *proof.nodes[1:]))
    return not verify_dag_parent_commit(
        mutated,
        kernel.config,
        kernel.verification_context(),
    )


def run_demo() -> dict:
    config = Grid2DConfig(
        width=WIDTH,
        height=HEIGHT,
        memory_decay=0.0,
        mask="checkerboard",
        neighborhood="von_neumann",
    )
    initial = "A" * CELLS

    dense = CommittedProofKernel(
        initial,
        config=config,
        scheduler_cls=InstrumentedDenseGrid2D,
        proof_density=1.0,
        proof_seed=PROOF_SEED,
    )
    sparse = CommittedProofKernel(
        initial,
        config=config,
        scheduler_cls=DirtyNodeGrid2D,
        proof_density=1.0,
        proof_seed=PROOF_SEED,
    )

    per_tick_equal = True
    for stimulus in incident_schedule():
        dense.step(stimulus)
        sparse.step(stimulus)
        per_tick_equal = per_tick_equal and dense.state_string() == sparse.state_string()

    dense_state = dense.state_string()
    sparse_state = sparse.state_string()
    dense_counters = dense.scheduler_counters()
    sparse_counters = sparse.scheduler_counters()

    semantic_equal = (
        per_tick_equal
        and dense_state == sparse_state
        and dense.transitions == sparse.transitions
    )
    replay_equal = dense.replay() == dense_state and sparse.replay() == sparse_state
    proof_valid = dense.verify_proof() and sparse.verify_proof()
    proof_equal = (
        dense.proof().canonical_bytes() == sparse.proof().canonical_bytes()
        and dense.verification_context() == sparse.verification_context()
    )
    mutation_rejected = _mutated_proof_is_rejected(sparse)

    if not semantic_equal:
        raise RuntimeError("dense and sparse application semantics diverged")
    if not replay_equal:
        raise RuntimeError("transition replay did not reconstruct final state")
    if not proof_valid or not proof_equal:
        raise RuntimeError("committed proof was invalid or scheduler-dependent")
    if not mutation_rejected:
        raise RuntimeError("mutated transition claim was accepted")
    if sparse.total_completed_transitions == 0:
        raise RuntimeError("incident schedule produced no transitions")

    dense_evaluations = dense_counters.node_evaluations
    sparse_evaluations = sparse_counters.node_evaluations
    reduction = 1.0 - (sparse_evaluations / dense_evaluations)
    proof_bytes = sparse.proof().canonical_bytes()

    return {
        "demo_id": "COSMIC-VERIFIED-INCIDENT-MAP/v0.1",
        "status": "PASS",
        "application_mapping": {
            "A": "nominal",
            "M": "elevated_or_transition",
            "C": "critical",
        },
        "map": {
            "width": WIDTH,
            "height": HEIGHT,
            "cells": CELLS,
            "logical_ticks": len(incident_schedule()),
            "primary_incident_sites": [_site(*coord) for coord in PRIMARY_INCIDENT],
            "secondary_incident_sites": [_site(*coord) for coord in SECONDARY_INCIDENT],
        },
        "correctness": {
            "per_tick_dense_sparse_equal": per_tick_equal,
            "final_state_equal": dense_state == sparse_state,
            "transition_count_equal": dense.transitions == sparse.transitions,
            "transition_replay_equal": replay_equal,
            "dense_proof_valid": dense.verify_proof(),
            "sparse_proof_valid": sparse.verify_proof(),
            "proof_representation_equal": proof_equal,
            "mutated_transition_claim_rejected": mutation_rejected,
        },
        "result": {
            "completed_transitions": sparse.total_completed_transitions,
            "audited_transitions": sparse.proof_metrics()["audited_transitions"],
            "final_phase_counts": _phase_counts(sparse_state),
            "final_state_sha256": hashlib.sha256(sparse_state.encode("ascii")).hexdigest(),
        },
        "execution_work": {
            "dense": asdict(dense_counters),
            "sparse": asdict(sparse_counters),
            "sparse_node_evaluation_reduction_fraction": reduction,
            "sparse_node_evaluation_reduction_percent": round(reduction * 100.0, 4),
        },
        "proof_work": sparse.proof_metrics(),
        "evidence": {
            "proof_canonical_bytes": len(proof_bytes),
            "proof_sha256": hashlib.sha256(proof_bytes).hexdigest(),
            "proof_density": 1.0,
            "proof_seed": PROOF_SEED,
        },
        "claim_boundary": (
            "Deterministic software application demo over the frozen "
            "COSMIC-KERNEL-05 mechanisms. It does not establish calibrated "
            "operational risk, measured energy, FPGA performance, or a "
            "Bardo-specific advantage."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    args = parser.parse_args()
    result = run_demo()
    print(
        json.dumps(
            result,
            sort_keys=True,
            indent=None if args.compact else 2,
            separators=(",", ":") if args.compact else None,
        )
    )


if __name__ == "__main__":
    main()
