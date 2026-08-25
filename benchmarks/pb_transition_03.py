"""PB-TRANSITION-03 partial common trust-boundary adapter for MORPHOS.

MORPHOS is credited only where the current A/M/C simulator has an executable
mapping: VALID and UNKNOWN/insufficient drive. Authority freshness, replay,
logical conflict, and outcome-grounding semantics remain explicitly unassessed.
"""

from __future__ import annotations

import argparse
import json
import time

from morphos.simulator import Lattice, Phase

BENCHMARK_ID = "PB-TRANSITION-03"
VERSION = "0.1"
PROTOCOL = "PB-T03/v0.1 authorization-freshness-replay-conflict-outcome"
FAULT_KINDS = (
    "UNKNOWN",
    "STALE_AUTHORITY",
    "REPLAY",
    "CONFLICT",
    "FALSE_SUCCESS",
)


def run(trials: int = 10_000, contamination_rate: float = 0.10) -> dict:
    if trials <= 0:
        raise ValueError("trials must be positive")
    if not 0 <= contamination_rate <= 1:
        raise ValueError("contamination_rate must be between 0 and 1")

    bad_count = round(trials * contamination_rate)
    bad_seen = 0
    counts = {"VALID": 0, **{kind: 0 for kind in FAULT_KINDS}}
    per_kind = {
        "VALID": {"status": "supported", "trials": 0, "oracle_correct": 0},
        "UNKNOWN": {"status": "supported", "trials": 0, "oracle_correct": 0},
        "STALE_AUTHORITY": {"status": "unsupported", "trials": 0},
        "REPLAY": {"status": "unsupported", "trials": 0},
        "CONFLICT": {"status": "unsupported", "trials": 0},
        "FALSE_SUCCESS": {"status": "unsupported", "trials": 0},
    }

    oracle_correct = 0
    unsafe_dispatches = 0
    missed_valid = 0
    transition_steps = 0
    phase_changes = 0
    simulated_drive = 0.0

    started = time.perf_counter_ns()
    for index in range(trials):
        contaminated = ((index + 1) * bad_count) // trials > (
            index * bad_count
        ) // trials
        if contaminated:
            kind = FAULT_KINDS[bad_seen % len(FAULT_KINDS)]
            bad_seen += 1
        else:
            kind = "VALID"
        counts[kind] += 1
        per_kind[kind]["trials"] += 1

        if kind not in {"VALID", "UNKNOWN"}:
            continue

        source = index % 2
        target = 1 - source
        source_phase = Phase.AMORPHOUS if source == 0 else Phase.CRYSTALLINE
        target_phase = Phase.CRYSTALLINE if target == 1 else Phase.AMORPHOUS
        lattice = Lattice(size=1, initial=source_phase)
        direction = 1.0 if target > source else -1.0
        magnitude = 0.45 if kind == "VALID" else 0.10

        for _ in range(2):
            lattice.step(direction * magnitude)
            transition_steps += 1
            simulated_drive += lattice.cells[0].energy

        phase_changes += lattice.transition_count
        final_phase = lattice.cells[0].phase

        if kind == "VALID":
            if final_phase is target_phase:
                oracle_correct += 1
                per_kind[kind]["oracle_correct"] += 1
            else:
                missed_valid += 1
        else:
            if final_phase is source_phase:
                oracle_correct += 1
                per_kind[kind]["oracle_correct"] += 1
            else:
                unsafe_dispatches += 1

    elapsed_ns = time.perf_counter_ns() - started
    assessed_trials = counts["VALID"] + counts["UNKNOWN"]
    unassessed_trials = trials - assessed_trials
    seconds = elapsed_ns / 1_000_000_000

    return {
        "benchmark_id": BENCHMARK_ID,
        "version": VERSION,
        "protocol": PROTOCOL,
        "architecture": "COSMIC ORGANICS / MORPHOS",
        "implementation": "MORPHOS-0 single-cell A/M/C phase-transition reference simulator",
        "status": "executed_partial",
        "trials": trials,
        "contamination_rate": contamination_rate,
        "valid_trials": counts["VALID"],
        "adversarial_trials": trials - counts["VALID"],
        "failure_kind_coverage": 0.2,
        "stream_semantic_coverage": assessed_trials / trials,
        "supported_fault_kinds": ["UNKNOWN"],
        "unsupported_fault_kinds": [
            "STALE_AUTHORITY",
            "REPLAY",
            "CONFLICT",
            "FALSE_SUCCESS",
        ],
        "assessed_trials": assessed_trials,
        "unassessed_trials": unassessed_trials,
        "oracle_correct_assessed_trials": oracle_correct,
        "oracle_accuracy_on_assessed": oracle_correct / assessed_trials,
        "unsafe_authorization_dispatches_on_assessed": unsafe_dispatches,
        "false_success_claims_on_assessed": 0,
        "missed_valid_dispatches_on_assessed": missed_valid,
        "evidence_kind": "deterministic_phase_transition_trace",
        "per_kind": per_kind,
        "elapsed_ns": elapsed_ns,
        "assessed_trials_per_sec": assessed_trials / seconds if seconds else 0.0,
        "native_steps_total": transition_steps,
        "phase_changes_total": phase_changes,
        "simulated_drive_magnitude_total": simulated_drive,
        "claim_boundary": (
            "PB-T03 credits MORPHOS only for VALID and UNKNOWN through the real "
            "A/M/C threshold dynamics. STALE_AUTHORITY, REPLAY, CONFLICT, and "
            "FALSE_SUCCESS have no current native executable mapping and are "
            "unassessed, never counted as prevented."
        ),
        "cost_note": (
            "simulated drive magnitude is dimensionless model data, not physical "
            "energy, joules, hardware cycles, area, or silicon power"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MORPHOS PB-TRANSITION-03.")
    parser.add_argument("--trials", type=int, default=10_000)
    parser.add_argument("--contamination", type=float, default=0.10)
    args = parser.parse_args()
    print(json.dumps(run(args.trials, args.contamination), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
