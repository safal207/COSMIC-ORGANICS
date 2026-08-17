"""Diagnostic-only classification of the four W8.4 fresh-confirmation misses."""
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
from morphos.witness_causal_locality import CausalLocalityAuthorityGrid2D

CORPORA = [
    {"width": 7, "height": 7, "seed": 202608167012, "samples": 64},
    {"width": 7, "height": 7, "seed": 202608167013, "samples": 64},
    {"width": 9, "height": 9, "seed": 202608167023, "samples": 64},
]
EVAL_HORIZON = 8
TRACE_HORIZON = 12
MAX_TARGETS = 8
TRIALS_PER_TARGET = 6


def _errors(model: CausalLocalityAuthorityGrid2D, target: str) -> list[int]:
    return [
        i
        for i, (actual, expected) in enumerate(zip(model.state_string(), target))
        if actual != expected
    ]


def _trace(target: str, source: int, config, hierarchy, mirror_law) -> tuple[CausalLocalityAuthorityGrid2D, list[dict], int | None]:
    model = CausalLocalityAuthorityGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
    )
    _corrupt_all(model, source)
    timeline = []
    first_exact_tick = None
    for tick in range(1, TRACE_HORIZON + 1):
        before = {
            "handoff": model.handoff_events,
            "erasure": model.erasure_handoff_events,
            "margin": model.margin_completion_events,
            "path_m": model.path_completion_m_events,
            "closure": model.executable_closure_events,
            "history": model.history_pair_decode_events,
            "locality": model.locality_pair_decode_events,
        }
        model.step(0.0)
        errors = _errors(model, target)
        if not errors and first_exact_tick is None:
            first_exact_tick = tick
        bad_rows, bad_columns = model.syndrome()
        timeline.append(
            {
                "tick": tick,
                "source_phase": model.states[source],
                "source_target": target[source],
                "source_repaired": model.states[source] == target[source],
                "errors": errors,
                "syndrome_rows": list(bad_rows),
                "syndrome_columns": list(bad_columns),
                "latched_index": model.latched_index,
                "latched_target": model.latched_target,
                "protected_targets": {str(k): v for k, v in model.protected_targets.items()},
                "fence_active": model.selective_fence_active,
                "max_repair_set_size": model.max_repair_set_size,
                "handoff_delta": model.handoff_events - before["handoff"],
                "erasure_handoff_delta": model.erasure_handoff_events - before["erasure"],
                "margin_completion_delta": model.margin_completion_events - before["margin"],
                "path_m_completion_delta": model.path_completion_m_events - before["path_m"],
                "executable_closure_delta": model.executable_closure_events - before["closure"],
                "history_pair_decode_delta": model.history_pair_decode_events - before["history"],
                "locality_pair_decode_delta": model.locality_pair_decode_events - before["locality"],
            }
        )
    return model, timeline, first_exact_tick


def main() -> None:
    base = _manifest()
    misses = []
    checked_trials = 0

    for corpus in CORPORA:
        width, height = corpus["width"], corpus["height"]
        cells = width * height
        config, hierarchy = _s2_components(base, width, height)
        mirror_law = _m2_law(base)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(corpus["seed"], corpus["samples"], cells),
            config,
            hierarchy,
            6,
        )[:MAX_TARGETS]
        for target_index, target in enumerate(targets):
            sources = _noise_indices(
                corpus["seed"], target_index, cells, TRIALS_PER_TARGET
            )
            for trial_index, source in enumerate(sources):
                checked_trials += 1
                quick = _run(
                    CausalLocalityAuthorityGrid2D,
                    target=target,
                    indices=[source],
                    config=config,
                    hierarchy=hierarchy,
                    m2_law=mirror_law,
                    witness_drive=0.25,
                    witness_commit_delay=8,
                    horizon=EVAL_HORIZON,
                )
                if quick.state_string() == target:
                    continue
                model, timeline, first_exact_tick = _trace(
                    target, source, config, hierarchy, mirror_law
                )
                errors_at_8 = timeline[EVAL_HORIZON - 1]["errors"]
                errors_at_12 = timeline[-1]["errors"]
                misses.append(
                    {
                        "width": width,
                        "height": height,
                        "seed": corpus["seed"],
                        "target_index": target_index,
                        "trial_index": trial_index,
                        "source": source,
                        "source_target": target[source],
                        "first_exact_tick": first_exact_tick,
                        "late_recovery_by_12": first_exact_tick is not None and first_exact_tick > EVAL_HORIZON,
                        "persistent_through_12": bool(errors_at_12),
                        "source_repaired_at_8": timeline[EVAL_HORIZON - 1]["source_repaired"],
                        "source_repaired_at_12": timeline[-1]["source_repaired"],
                        "errors_at_8": errors_at_8,
                        "errors_at_12": errors_at_12,
                        "final_error_count": len(errors_at_12),
                        "handoff_events": model.handoff_events,
                        "erasure_handoff_events": model.erasure_handoff_events,
                        "margin_completion_events": model.margin_completion_events,
                        "path_m_completion_events": model.path_completion_m_events,
                        "executable_closure_events": model.executable_closure_events,
                        "history_pair_decode_events": model.history_pair_decode_events,
                        "locality_pair_decode_events": model.locality_pair_decode_events,
                        "max_repair_set_size": model.max_repair_set_size,
                        "handoff_history": [list(pair) for pair in model.handoff_history],
                        "timeline": timeline,
                    }
                )

    if len(misses) != 4:
        raise AssertionError(f"expected four frozen tick-8 misses, got {len(misses)}")

    summary = {
        "checked_trials": checked_trials,
        "tick8_misses": len(misses),
        "late_recovery_by_12": sum(row["late_recovery_by_12"] for row in misses),
        "persistent_through_12": sum(row["persistent_through_12"] for row in misses),
        "source_repaired_at_8": sum(row["source_repaired_at_8"] for row in misses),
        "source_repaired_at_12": sum(row["source_repaired_at_12"] for row in misses),
        "misses_with_handoff": sum(row["handoff_events"] > 0 for row in misses),
        "misses_with_erasure_handoff": sum(row["erasure_handoff_events"] > 0 for row in misses),
        "misses_with_executable_closure": sum(row["executable_closure_events"] > 0 for row in misses),
        "misses_with_history_pair": sum(row["history_pair_decode_events"] > 0 for row in misses),
        "misses_with_locality_pair": sum(row["locality_pair_decode_events"] > 0 for row in misses),
    }
    report = {
        "schema": "cosmic-organics/w84-fresh-miss-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_confirmation_head": "452ccd9bf103c55558ed72e52dc503c30f80ceae",
        "summary": summary,
        "misses": misses,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
