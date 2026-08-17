"""Diagnostic-only trace of the sole W8.3 fresh-confirmation miss.

No W8.3 mechanism, threshold, amplitude, coupling, parity code, seed, horizon,
or gate is changed. The script finds the unique W8.2/W8.3 miss in frozen
9x9 seed 202608166023 and traces the W8.3 transaction through tick 12.
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
from benchmarks.run_w4_confirmation import _run
from morphos.witness import WitnessLaw
from morphos.witness_executable_margin import ExecutableMarginClosureGrid2D
from morphos.witness_history_pair import HistoryAwarePairAuthorityGrid2D

SEED = 202608166023
WIDTH = HEIGHT = 9
SAMPLES = 64
MAX_TARGETS = 8
TRIALS_PER_TARGET = 6
EVAL_HORIZON = 8
RETENTION_HORIZON = 12


def _errors(state: str, target: str) -> list[int]:
    return [i for i, (actual, expected) in enumerate(zip(state, target)) if actual != expected]


def _manual_trace(target: str, source: int, config, hierarchy, mirror_law) -> tuple[HistoryAwarePairAuthorityGrid2D, list[dict]]:
    model = HistoryAwarePairAuthorityGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
    )
    _corrupt_all(model, source)
    timeline = []
    for tick in range(1, RETENTION_HORIZON + 1):
        before = {
            "handoff": model.handoff_events,
            "erasure": model.erasure_handoff_events,
            "margin": model.margin_completion_events,
            "path_m": model.path_completion_m_events,
            "closure": model.executable_closure_events,
            "history": model.history_pair_decode_events,
        }
        model.step(0.0)
        bad_rows, bad_columns = model.syndrome()
        matchings = model._two_error_matchings()
        verified = sorted(model._verified_protected_indices())
        compatible = [
            list(pair)
            for pair in matchings
            if not any(index in verified for index in pair)
        ]
        timeline.append(
            {
                "tick": tick,
                "source_phase": model.states[source],
                "source_target": target[source],
                "source_verified": (
                    source in model.protected_targets
                    and model.protected_targets[source] == target[source]
                    and model.states[source] == target[source]
                ),
                "errors": _errors(model.state_string(), target),
                "syndrome_rows": list(bad_rows),
                "syndrome_columns": list(bad_columns),
                "two_error_matchings": [list(pair) for pair in matchings],
                "verified_protected_indices": verified,
                "history_compatible_matchings": compatible,
                "latched_index": model.latched_index,
                "latched_target": model.latched_target,
                "protected_targets": {
                    str(index): endpoint
                    for index, endpoint in model.protected_targets.items()
                },
                "fence_active": model.selective_fence_active,
                "max_repair_set_size": model.max_repair_set_size,
                "handoff_delta": model.handoff_events - before["handoff"],
                "erasure_handoff_delta": model.erasure_handoff_events - before["erasure"],
                "margin_completion_delta": model.margin_completion_events - before["margin"],
                "path_m_completion_delta": model.path_completion_m_events - before["path_m"],
                "executable_closure_delta": model.executable_closure_events - before["closure"],
                "history_pair_decode_delta": model.history_pair_decode_events - before["history"],
            }
        )
    return model, timeline


def main() -> None:
    base = _manifest()
    config, hierarchy = _s2_components(base, WIDTH, HEIGHT)
    mirror_law = _m2_law(base)
    targets = _fixed_binary_targets(
        _sha_binary_seeds(SEED, SAMPLES, WIDTH * HEIGHT),
        config,
        hierarchy,
        6,
    )[:MAX_TARGETS]

    misses = []
    for target_index, target in enumerate(targets):
        indices = _noise_indices(SEED, target_index, WIDTH * HEIGHT, TRIALS_PER_TARGET)
        for trial_index, source in enumerate(indices):
            kwargs = dict(
                target=target,
                indices=[source],
                config=config,
                hierarchy=hierarchy,
                m2_law=mirror_law,
                witness_drive=0.25,
                witness_commit_delay=8,
            )
            w82 = _run(
                ExecutableMarginClosureGrid2D,
                horizon=EVAL_HORIZON,
                **kwargs,
            )
            w83 = _run(
                HistoryAwarePairAuthorityGrid2D,
                horizon=EVAL_HORIZON,
                **kwargs,
            )
            if w83.state_string() == target:
                continue
            model, timeline = _manual_trace(
                target, source, config, hierarchy, mirror_law
            )
            final_errors = _errors(model.state_string(), target)
            source_repaired = model.states[source] == target[source]
            misses.append(
                {
                    "target_index": target_index,
                    "trial_index": trial_index,
                    "source": source,
                    "source_target": target[source],
                    "w82_exact_at_8": w82.state_string() == target,
                    "w83_exact_at_8": False,
                    "w83_exact_at_12": model.state_string() == target,
                    "source_repaired_at_12": source_repaired,
                    "errors_at_12": final_errors,
                    "handoff_events": model.handoff_events,
                    "erasure_handoff_events": model.erasure_handoff_events,
                    "margin_completion_events": model.margin_completion_events,
                    "path_m_completion_events": model.path_completion_m_events,
                    "executable_closure_events": model.executable_closure_events,
                    "history_pair_decode_events": model.history_pair_decode_events,
                    "max_repair_set_size": model.max_repair_set_size,
                    "handoff_history": [list(pair) for pair in model.handoff_history],
                    "timeline": timeline,
                }
            )

    if len(misses) != 1:
        raise AssertionError(f"expected exactly one frozen W8.3 miss, got {len(misses)}")

    miss = misses[0]
    final_errors = miss["errors_at_12"]
    classification = {
        "source_not_repaired": not miss["source_repaired_at_12"],
        "source_repaired_other_errors_remain": (
            miss["source_repaired_at_12"] and bool(final_errors)
        ),
        "has_handoff": miss["handoff_events"] > 0,
        "has_erasure_handoff": miss["erasure_handoff_events"] > 0,
        "has_executable_closure": miss["executable_closure_events"] > 0,
        "has_history_pair_decode": miss["history_pair_decode_events"] > 0,
        "final_error_count": len(final_errors),
    }
    report = {
        "schema": "cosmic-organics/w83-fresh-miss-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_confirmation_pr": 41,
        "seed": SEED,
        "miss": miss,
        "classification": classification,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
