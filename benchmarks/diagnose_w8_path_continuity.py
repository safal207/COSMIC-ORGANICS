"""Diagnostic-only trace of the four frozen W8-v0 development failures.

No mechanism or gate is changed. The trace asks whether entry margin completion
moves the owned source into M but fails to preserve endpoint direction through
the remaining M->target half of the path.
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
from morphos.witness_margin_completion import MarginCompletionAuthorityGrid2D

CASES = [
    {"width": 7, "seed": 202608164011, "target_index": 3, "trial_index": 1},
    {"width": 7, "seed": 202608164012, "target_index": 3, "trial_index": 1},
    {"width": 7, "seed": 202608164013, "target_index": 6, "trial_index": 0},
    {"width": 9, "seed": 202608164022, "target_index": 3, "trial_index": 1},
]


def _errors(model, target: str) -> list[int]:
    return [i for i, (actual, expected) in enumerate(zip(model.states, target)) if actual != expected]


def run_diagnostic() -> dict:
    base = _manifest()
    rows = []
    aggregate = {
        "cases": 0,
        "entered_m": 0,
        "m_returned_to_wrong_binary": 0,
        "m_reached_target": 0,
        "completion_repeated": 0,
        "exact_recovery": 0,
    }

    for case in CASES:
        width = case["width"]
        cells = width * width
        config, hierarchy = _s2_components(base, width, width)
        target = _fixed_binary_targets(
            _sha_binary_seeds(case["seed"], 64, cells), config, hierarchy, 6
        )[:8][case["target_index"]]
        source = _noise_indices(
            case["seed"], case["target_index"], cells, 6
        )[case["trial_index"]]
        model = MarginCompletionAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        _corrupt_all(model, source)
        wrong = model.states[source]
        endpoint = target[source]
        timeline = []
        entered_m = False
        returned_wrong = False
        reached_target_from_m = False
        previous_phase = wrong

        for tick in range(1, 13):
            completions_before = model.margin_completion_events
            phase_before = model.states[source]
            model.step(0.0)
            phase_after = model.states[source]
            completion_delta = model.margin_completion_events - completions_before

            if phase_after == "M":
                entered_m = True
            if phase_before == "M" and phase_after == wrong:
                returned_wrong = True
            if phase_before == "M" and phase_after == endpoint:
                reached_target_from_m = True

            timeline.append(
                {
                    "tick": tick,
                    "source_phase_before": phase_before,
                    "source_phase_after": phase_after,
                    "completion_event_delta": completion_delta,
                    "completion_total": model.margin_completion_total,
                    "completion_max": model.margin_completion_max,
                    "latched_index": model.latched_index,
                    "latched_target": model.latched_target,
                    "fence_active": model.selective_fence_active,
                    "localized": model.localized_error_index(),
                    "protected_targets": {str(k): v for k, v in model.protected_targets.items()},
                    "errors": _errors(model, target),
                }
            )
            previous_phase = phase_after

        exact = model.state_string() == target
        aggregate["cases"] += 1
        aggregate["entered_m"] += int(entered_m)
        aggregate["m_returned_to_wrong_binary"] += int(returned_wrong)
        aggregate["m_reached_target"] += int(reached_target_from_m)
        aggregate["completion_repeated"] += int(model.margin_completion_events > 1)
        aggregate["exact_recovery"] += int(exact)
        rows.append(
            {
                **case,
                "source": source,
                "wrong_binary": wrong,
                "target_endpoint": endpoint,
                "entered_m": entered_m,
                "m_returned_to_wrong_binary": returned_wrong,
                "m_reached_target": reached_target_from_m,
                "completion_events": model.margin_completion_events,
                "exact_recovery_at_12": exact,
                "timeline": timeline,
            }
        )

    return {
        "schema": "cosmic-organics/w8-path-continuity-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_failed_w8_head": "86f9b7f9a964307f34b7d94b14916b1d6494aa62",
        "aggregate": aggregate,
        "cases": rows,
        "decision_contract": "if M repeatedly returns to the still-owned wrong binary endpoint, diagnose directional path continuity before changing any global amplitude or threshold",
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
