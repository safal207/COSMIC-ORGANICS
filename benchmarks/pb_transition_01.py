"""ProofBit PB-TRANSITION-01 adapter for frozen MORPHOS-W8.5.

This adapter does not reinterpret MORPHOS as a ProofBit guard processor. It runs
MORPHOS's own preregistered W8.5 transition/recovery protocol and emits a compact,
machine-readable scorecard for cross-architecture research.
"""
from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter_ns

from benchmarks.run_w85_opportunity_continuation import run_continuation

MANIFEST = Path(__file__).with_name("w85_opportunity_continuation_manifest.json")


def build_report() -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))

    start = perf_counter_ns()
    source = run_continuation()
    elapsed_ns = perf_counter_ns() - start

    if source["decision"] != "TRANSFER_PASS":
        raise RuntimeError(
            "PB-TRANSITION-01 requires the frozen MORPHOS-W8.5 transfer contract "
            f"to pass; observed {source['decision']}"
        )

    summary = source["summary"]
    trials = int(summary["observed_trials"])
    opportunities = int(summary["fresh_w84_misses"])
    rescues = int(summary["multi_erasure_rescues_of_w84_misses"])

    return {
        "benchmark_id": "PB-TRANSITION-01",
        "version": "0.1",
        "architecture": "COSMIC ORGANICS / MORPHOS",
        "implementation": "MORPHOS-W8.5 transition-state GF(2) handoff",
        "status": "executed",
        "scope": (
            "Transition/recovery benchmark on MORPHOS's own deterministic lattice "
            "semantics. Raw throughput is not directly rankable against PB-ARCH-01 "
            "guard decisions or accelerator FLOPS."
        ),
        "frozen_provenance": {
            "w85_development_head": source["frozen_w85_development_head"],
            "source_confirmation_head": source[
                "source_inconclusive_confirmation_head"
            ],
            "mechanism_blob_sha": protocol["frozen_mechanism_blob_sha"],
            "mechanism_blob_matches_frozen": summary[
                "mechanism_blob_matches_frozen"
            ],
            "preregistered_stopping_rule": source["stopping_rule"],
            "continuation_only_no_retuning": source[
                "continuation_only_no_retuning"
            ],
        },
        "workload": {
            "observed_batches": summary["observed_batches"],
            "observed_corpora": summary["observed_corpora"],
            "observed_trials": trials,
            "opportunity_batch": summary["opportunity_batch"],
            "transition_contract": (
                "one verified source + exactly two M transition cells + unique "
                "GF(2) committed-parity solution + full virtual parity replay"
            ),
        },
        "utility": {
            "predecessor_failures": opportunities,
            "causal_rescues": rescues,
            "causal_rescue_rate": rescues / opportunities if opportunities else None,
            "minimum_exact_recovery_at_8": summary[
                "minimum_w85_recovery_at_8"
            ],
            "minimum_exact_recovery_at_12": summary[
                "minimum_w85_recovery_at_12"
            ],
            "previous_successes_regressed": summary[
                "previous_w84_successes_regressed"
            ],
            "multi_erasure_decode_events": summary[
                "multi_erasure_decode_events"
            ],
            "multi_erasure_added_targets": summary[
                "multi_erasure_added_targets"
            ],
        },
        "proof": {
            "decision": source["decision"],
            "recovery_and_controls_pass": summary[
                "recovery_and_controls_pass"
            ],
            "minimum_corrupted_witness_causal_drop_pp": summary[
                "minimum_causal_drop_when_witness_corrupted"
            ],
            "all_zero_drive_exact_w84": summary[
                "all_zero_drive_exact_w84"
            ],
            "minimum_primary_only_delta_vs_w84": summary[
                "minimum_primary_only_delta_vs_w84"
            ],
        },
        "cost_speed": {
            "elapsed_ns": elapsed_ns,
            "trials_per_sec": trials / (elapsed_ns / 1_000_000_000),
            "note": (
                "Wall-clock Python simulator throughput on the current runner. "
                "It includes the complete frozen continuation/control evaluation "
                "and is not a hardware-performance claim."
            ),
        },
        "claim_boundary": source["scope_boundary"],
    }


def main() -> None:
    print(json.dumps(build_report(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
