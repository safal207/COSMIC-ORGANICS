"""PB-TRANSITION-02 common binary-endpoint transition adapter for MORPHOS.

This deliberately uses MORPHOS-0's real A/M/C phase-transition simulator on a
single-cell lattice. It is a software research benchmark, not a calibrated
physical-energy or silicon-performance claim.
"""

from __future__ import annotations

import argparse
import json
import time

from morphos.simulator import Lattice, Phase

PROTOCOL = (
    "PB-T02/v0.1 binary-endpoint alternating-direction "
    "deterministic-insufficient-support"
)


def _is_insufficient(index: int, trials: int, insufficient_count: int) -> bool:
    return ((index + 1) * insufficient_count) // trials > (
        index * insufficient_count
    ) // trials


def run(trials: int = 10_000, insufficient_rate: float = 0.10) -> dict:
    if trials <= 0:
        raise ValueError("trials must be positive")
    if not 0 <= insufficient_rate <= 1:
        raise ValueError("insufficient_rate must be between 0 and 1")

    insufficient_count = round(trials * insufficient_rate)
    valid_trials = 0
    insufficient_trials = 0
    source_0_trials = 0
    source_1_trials = 0
    correct_valid_transitions = 0
    invalid_transitions_preserved = 0
    unsafe_invalid_transitions = 0
    missed_valid_transitions = 0
    justified_valid_transitions = 0
    transition_steps_total = 0
    phase_changes_total = 0
    simulated_drive_magnitude_total = 0.0

    started = time.perf_counter_ns()

    for index in range(trials):
        insufficient = _is_insufficient(index, trials, insufficient_count)
        source = index % 2
        target = 1 - source
        source_phase = Phase.AMORPHOUS if source == 0 else Phase.CRYSTALLINE
        target_phase = Phase.CRYSTALLINE if target == 1 else Phase.AMORPHOUS

        if source == 0:
            source_0_trials += 1
        else:
            source_1_trials += 1

        lattice = Lattice(size=1, initial=source_phase)
        direction = 1.0 if target > source else -1.0
        magnitude = 0.10 if insufficient else 0.45

        if insufficient:
            insufficient_trials += 1
        else:
            valid_trials += 1

        for _ in range(2):
            lattice.step(direction * magnitude)
            transition_steps_total += 1
            simulated_drive_magnitude_total += lattice.cells[0].energy

        phase_changes_total += lattice.transition_count
        final_phase = lattice.cells[0].phase

        if insufficient:
            if final_phase is source_phase:
                invalid_transitions_preserved += 1
            else:
                unsafe_invalid_transitions += 1
        elif final_phase is target_phase:
            correct_valid_transitions += 1
            justified_valid_transitions += 1
        else:
            missed_valid_transitions += 1

    elapsed_ns = time.perf_counter_ns() - started
    seconds = elapsed_ns / 1_000_000_000
    oracle_correct_trials = correct_valid_transitions + invalid_transitions_preserved

    return {
        "benchmark_id": "PB-TRANSITION-02",
        "version": "0.1",
        "protocol": PROTOCOL,
        "architecture": "COSMIC ORGANICS / MORPHOS",
        "implementation": "MORPHOS-0 single-cell A/M/C phase-transition reference simulator",
        "status": "executed",
        "trials": trials,
        "insufficient_support_rate": insufficient_rate,
        "valid_trials": valid_trials,
        "insufficient_support_trials": insufficient_trials,
        "source_0_trials": source_0_trials,
        "source_1_trials": source_1_trials,
        "correct_valid_transitions": correct_valid_transitions,
        "invalid_transitions_preserved": invalid_transitions_preserved,
        "unsafe_invalid_transitions": unsafe_invalid_transitions,
        "missed_valid_transitions": missed_valid_transitions,
        "oracle_correct_trials": oracle_correct_trials,
        "oracle_accuracy": oracle_correct_trials / trials,
        "native_justified_valid_transitions": justified_valid_transitions,
        "native_justification_coverage": (
            justified_valid_transitions / valid_trials if valid_trials else 0.0
        ),
        "evidence_kind": "deterministic_phase_transition_trace",
        "elapsed_ns": elapsed_ns,
        "trials_per_sec": trials / seconds if seconds else 0.0,
        "correct_useful_transitions_per_sec": (
            correct_valid_transitions / seconds if seconds else 0.0
        ),
        "justified_useful_throughput": (
            justified_valid_transitions / seconds if seconds else 0.0
        ),
        "native_steps_total": transition_steps_total,
        "phase_changes_total": phase_changes_total,
        "simulated_drive_magnitude_total": simulated_drive_magnitude_total,
        "cost_note": (
            "simulated drive magnitude is a dimensionless model quantity; it is "
            "not physical energy, joules, hardware cycles, area, or silicon power"
        ),
        "claim_boundary": (
            "PB-T02 maps sufficient support to two above-threshold MORPHOS pulses "
            "and insufficient support to two sub-threshold pulses. The resulting "
            "phase trace is transition evidence, not an authority proof equivalent "
            "to ProofBit or CaPU evidence."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MORPHOS PB-TRANSITION-02.")
    parser.add_argument("--trials", type=int, default=10_000)
    parser.add_argument("--insufficient", type=float, default=0.10)
    args = parser.parse_args()
    print(json.dumps(run(args.trials, args.insufficient), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
