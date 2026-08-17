"""Diagnostic-only phase trace for the four frozen W8.4 tick-8 misses.

No recovery mechanism, coefficient, threshold, parity code, seed, horizon, or
scientific gate changes. The purpose is to determine whether parity blindness
coincides with multiple transition-state (`M`) residuals, and whether persistent
cases evolve before binary observability becomes available.
"""
from __future__ import annotations

import json

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.witness import WitnessLaw
from morphos.witness_causal_locality import CausalLocalityAuthorityGrid2D

CASES = [
    {"width": 7, "height": 7, "seed": 202608167012, "target_index": 3, "trial_index": 5, "source": 19, "class": "persistent"},
    {"width": 7, "height": 7, "seed": 202608167013, "target_index": 1, "trial_index": 4, "source": 33, "class": "persistent"},
    {"width": 7, "height": 7, "seed": 202608167013, "target_index": 1, "trial_index": 5, "source": 32, "class": "late"},
    {"width": 9, "height": 9, "seed": 202608167023, "target_index": 3, "trial_index": 1, "source": 70, "class": "late"}
]
SAMPLES = 64
MAX_TARGETS = 8
TRIALS_PER_TARGET = 6
TRACE_HORIZON = 12


def _wrong(model, target: str) -> list[int]:
    return [i for i, (a, b) in enumerate(zip(model.states, target)) if a != b]


def _phase_partition(model, target: str) -> tuple[list[int], list[int]]:
    errors = _wrong(model, target)
    mixed = [i for i in errors if model.states[i] == "M"]
    wrong_binary = [i for i in errors if model.states[i] in ("A", "C")]
    return mixed, wrong_binary


def _replay(case: dict) -> dict:
    base = _manifest()
    width, height = case["width"], case["height"]
    cells = width * height
    config, hierarchy = _s2_components(base, width, height)
    targets = _fixed_binary_targets(
        _sha_binary_seeds(case["seed"], SAMPLES, cells), config, hierarchy, 6
    )[:MAX_TARGETS]
    target = targets[case["target_index"]]
    source = _noise_indices(
        case["seed"], case["target_index"], cells, TRIALS_PER_TARGET
    )[case["trial_index"]]
    if source != case["source"]:
        raise AssertionError(
            f"frozen source drift for {case}: expected {case['source']} got {source}"
        )

    model = CausalLocalityAuthorityGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=_m2_law(base),
        witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
    )
    _corrupt_all(model, source)

    timeline = []
    first_source_repaired = None
    first_all_residual_binary = None
    first_nonempty_syndrome = None
    first_decoder_event = None
    first_exact = None
    initial_post_source_error_set = None
    expanded_before_observable = False

    for tick in range(1, TRACE_HORIZON + 1):
        before_decoder = (
            model.handoff_events
            + model.erasure_handoff_events
            + model.history_pair_decode_events
            + model.locality_pair_decode_events
        )
        model.step(0.0)
        errors = _wrong(model, target)
        mixed, wrong_binary = _phase_partition(model, target)
        bad_rows, bad_columns = model.syndrome()
        source_repaired = model.states[source] == target[source]
        decoder_total = (
            model.handoff_events
            + model.erasure_handoff_events
            + model.history_pair_decode_events
            + model.locality_pair_decode_events
        )

        if source_repaired and first_source_repaired is None:
            first_source_repaired = tick
        if source_repaired and initial_post_source_error_set is None:
            initial_post_source_error_set = tuple(errors)
        if (
            source_repaired
            and errors
            and not mixed
            and first_all_residual_binary is None
        ):
            first_all_residual_binary = tick
        if (
            source_repaired
            and (bad_rows or bad_columns)
            and first_nonempty_syndrome is None
        ):
            first_nonempty_syndrome = tick
        if decoder_total > before_decoder and first_decoder_event is None:
            first_decoder_event = tick
        if not errors and first_exact is None:
            first_exact = tick

        if (
            source_repaired
            and first_nonempty_syndrome is None
            and initial_post_source_error_set is not None
            and tuple(errors) != initial_post_source_error_set
        ):
            expanded_before_observable = True

        timeline.append(
            {
                "tick": tick,
                "source_phase": model.states[source],
                "source_target": target[source],
                "source_repaired": source_repaired,
                "errors": errors,
                "error_phases": {str(i): model.states[i] for i in errors},
                "m_indices": mixed,
                "m_count": len(mixed),
                "wrong_binary_indices": wrong_binary,
                "wrong_binary_count": len(wrong_binary),
                "syndrome_rows": list(bad_rows),
                "syndrome_columns": list(bad_columns),
                "protected_targets": {str(k): v for k, v in model.protected_targets.items()},
                "handoff_events": model.handoff_events,
                "erasure_handoff_events": model.erasure_handoff_events,
                "history_pair_decode_events": model.history_pair_decode_events,
                "locality_pair_decode_events": model.locality_pair_decode_events,
            }
        )

    post_source_rows = [row for row in timeline if row["source_repaired"] and row["errors"]]
    max_m_after_source = max((row["m_count"] for row in post_source_rows), default=0)
    ticks_with_multiple_m_after_source = [
        row["tick"] for row in post_source_rows if row["m_count"] >= 2
    ]
    ticks_with_one_m_after_source = [
        row["tick"] for row in post_source_rows if row["m_count"] == 1
    ]

    return {
        **case,
        "source_target": target[source],
        "first_source_repaired_tick": first_source_repaired,
        "first_all_residual_binary_tick": first_all_residual_binary,
        "first_nonempty_syndrome_tick": first_nonempty_syndrome,
        "first_decoder_event_tick": first_decoder_event,
        "first_exact_tick": first_exact,
        "max_m_after_source_repair": max_m_after_source,
        "ticks_with_multiple_m_after_source": ticks_with_multiple_m_after_source,
        "ticks_with_one_m_after_source": ticks_with_one_m_after_source,
        "residual_changed_before_nonempty_syndrome": expanded_before_observable,
        "final_errors": timeline[-1]["errors"],
        "timeline": timeline,
    }


def main() -> None:
    rows = [_replay(case) for case in CASES]
    persistent = [row for row in rows if row["class"] == "persistent"]
    late = [row for row in rows if row["class"] == "late"]

    summary = {
        "cases": len(rows),
        "persistent_cases": len(persistent),
        "late_cases": len(late),
        "persistent_with_multiple_m_after_source": sum(
            bool(row["ticks_with_multiple_m_after_source"]) for row in persistent
        ),
        "late_with_multiple_m_after_source": sum(
            bool(row["ticks_with_multiple_m_after_source"]) for row in late
        ),
        "persistent_residual_changed_before_syndrome": sum(
            row["residual_changed_before_nonempty_syndrome"] for row in persistent
        ),
        "late_residual_changed_before_syndrome": sum(
            row["residual_changed_before_nonempty_syndrome"] for row in late
        ),
        "late_first_decoder_ticks": [row["first_decoder_event_tick"] for row in late],
        "late_first_exact_ticks": [row["first_exact_tick"] for row in late],
        "persistent_first_nonempty_syndrome_ticks": [
            row["first_nonempty_syndrome_tick"] for row in persistent
        ],
        "persistent_final_error_counts": [len(row["final_errors"]) for row in persistent],
    }

    report = {
        "schema": "cosmic-organics/w84-transition-observability-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_pr": 46,
        "summary": summary,
        "cases": rows,
        "decision_contract": (
            "consider a multi-transition-state observability experiment only if the "
            "persistent cases demonstrably contain multiple simultaneous M residuals "
            "during the post-source parity-blind interval; otherwise reject that hypothesis"
        ),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
