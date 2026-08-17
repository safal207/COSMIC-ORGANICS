"""Diagnostic-only replay of fresh W8.2 confirmation residuals.

No W8.2 mechanism, coefficient, threshold, seed, horizon, or gate is changed.
The script replays the single failing fresh corpus and records trial-level
trajectories for W8.1 misses, W8.2 rescues, and W8.2 residual failures.
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
from morphos.witness_path_completion import PathCompletionAuthorityGrid2D

SEED = 202608165022
WIDTH = HEIGHT = 9
SAMPLES = 64
MAX_TARGETS = 8
TRIALS_PER_TARGET = 6
EVAL_HORIZON = 8
RETENTION_HORIZON = 12
WITNESS_DRIVE = 0.25
WITNESS_COMMIT_DELAY = 8


def _errors(state: str, target: str) -> list[int]:
    return [i for i, (actual, expected) in enumerate(zip(state, target)) if actual != expected]


def _manual_w82(target: str, source: int, config, hierarchy, mirror_law):
    model = ExecutableMarginClosureGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(
            witness_drive=WITNESS_DRIVE,
            commit_delay=WITNESS_COMMIT_DELAY,
        ),
    )
    _corrupt_all(model, source)
    timeline = []
    state_at_8 = None
    for tick in range(1, RETENTION_HORIZON + 1):
        before_margin = model.margin_completion_events
        before_m = model.path_completion_m_events
        before_closure = model.executable_closure_events
        before_handoffs = model.handoff_events
        before_erasure = model.erasure_handoff_events
        model.step(0.0)
        state = model.state_string()
        if tick == EVAL_HORIZON:
            state_at_8 = state
        timeline.append(
            {
                "tick": tick,
                "source_phase": model.states[source],
                "errors": _errors(state, target),
                "latched_index": model.latched_index,
                "latched_target": model.latched_target,
                "protected_targets": {str(k): v for k, v in model.protected_targets.items()},
                "fence_active": model.selective_fence_active,
                "localized": model.last_localized_index,
                "margin_completion_delta": model.margin_completion_events - before_margin,
                "m_completion_delta": model.path_completion_m_events - before_m,
                "executable_closure_delta": model.executable_closure_events - before_closure,
                "handoff_delta": model.handoff_events - before_handoffs,
                "erasure_handoff_delta": model.erasure_handoff_events - before_erasure,
                "max_repair_set_size": model.max_repair_set_size,
            }
        )
    return model, state_at_8, timeline


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

    w81_misses = []
    w82_misses = []
    w82_rescues = []

    for target_index, target in enumerate(targets):
        indices = _noise_indices(SEED, target_index, WIDTH * HEIGHT, TRIALS_PER_TARGET)
        for trial_index, source in enumerate(indices):
            kwargs = dict(
                target=target,
                indices=[source],
                config=config,
                hierarchy=hierarchy,
                m2_law=mirror_law,
                witness_drive=WITNESS_DRIVE,
                witness_commit_delay=WITNESS_COMMIT_DELAY,
            )
            w81 = _run(
                PathCompletionAuthorityGrid2D,
                horizon=EVAL_HORIZON,
                **kwargs,
            )
            w81_ok = w81.state_string() == target
            w82, state_at_8, timeline = _manual_w82(
                target, source, config, hierarchy, mirror_law
            )
            w82_ok8 = state_at_8 == target
            w82_ok12 = w82.state_string() == target
            row = {
                "target_index": target_index,
                "trial_index": trial_index,
                "source": source,
                "source_target": target[source],
                "source_final_phase": w82.states[source],
                "w81_exact_at_8": w81_ok,
                "w82_exact_at_8": w82_ok8,
                "w82_exact_at_12": w82_ok12,
                "errors_at_12": _errors(w82.state_string(), target),
                "margin_completion_events": w82.margin_completion_events,
                "path_m_completion_events": w82.path_completion_m_events,
                "executable_closure_events": w82.executable_closure_events,
                "executable_closure_steps": w82.executable_closure_steps,
                "handoff_events": w82.handoff_events,
                "erasure_handoff_events": w82.erasure_handoff_events,
                "handoff_history": [list(pair) for pair in w82.handoff_history],
                "max_repair_set_size": w82.max_repair_set_size,
                "timeline": timeline,
            }
            if not w81_ok:
                w81_misses.append(row)
            if not w82_ok12:
                w82_misses.append(row)
            if not w81_ok and w82_ok12:
                w82_rescues.append(row)

    report = {
        "schema": "cosmic-organics/w82-fresh-residual-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "seed": SEED,
        "trials": len(targets) * TRIALS_PER_TARGET,
        "summary": {
            "w81_misses": len(w81_misses),
            "w82_rescues_of_w81_misses": len(w82_rescues),
            "w82_residual_failures": len(w82_misses),
            "residual_source_not_repaired": sum(
                row["source_final_phase"] != row["source_target"] for row in w82_misses
            ),
            "residual_source_repaired_but_other_errors_remain": sum(
                row["source_final_phase"] == row["source_target"]
                and bool(row["errors_at_12"])
                for row in w82_misses
            ),
            "residual_with_executable_closure": sum(
                row["executable_closure_events"] > 0 for row in w82_misses
            ),
            "residual_with_handoff": sum(row["handoff_events"] > 0 for row in w82_misses),
            "residual_with_erasure_handoff": sum(
                row["erasure_handoff_events"] > 0 for row in w82_misses
            ),
        },
        "w82_rescues": w82_rescues,
        "w82_residual_failures": w82_misses,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
