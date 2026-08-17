"""Diagnostic-only test of repair-history-aware two-error disambiguation.

This does not change MORPHOS-W8.2. It replays the two frozen residuals from
W8.2-R1 and asks whether the post-source 2x2 parity ambiguity becomes unique
when the already protected, independently verified source is excluded from
candidate error matchings.
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
from morphos.witness_executable_margin import ExecutableMarginClosureGrid2D

SEED = 202608165022
WIDTH = HEIGHT = 9
SAMPLES = 64
TARGET_INDEX = 5
TRIALS_PER_TARGET = 6
CASES = (
    {"trial_index": 3, "expected_source": 47, "expected_errors": [46, 56]},
    {"trial_index": 5, "expected_source": 77, "expected_errors": [68, 76]},
)


def _errors(state: str, target: str) -> list[int]:
    return [i for i, (actual, expected) in enumerate(zip(state, target)) if actual != expected]


def _matchings(rows: tuple[int, ...], cols: tuple[int, ...]) -> list[list[int]]:
    if len(rows) != 2 or len(cols) != 2:
        return []
    r0, r1 = rows
    c0, c1 = cols
    return [
        sorted([r0 * WIDTH + c0, r1 * WIDTH + c1]),
        sorted([r0 * WIDTH + c1, r1 * WIDTH + c0]),
    ]


def _replay_case(target: str, source: int, config, hierarchy, mirror_law) -> tuple[ExecutableMarginClosureGrid2D, list[dict]]:
    model = ExecutableMarginClosureGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
    )
    _corrupt_all(model, source)
    timeline = []
    for tick in range(1, 3):
        model.step(0.0)
        rows, cols = model.syndrome()
        current_errors = _errors(model.state_string(), target)
        raw = _matchings(tuple(rows), tuple(cols))
        verified_source = (
            source in model.protected_targets
            and model.protected_targets[source] == target[source]
            and model.states[source] == target[source]
        )
        compatible = [m for m in raw if not (verified_source and source in m)]
        timeline.append(
            {
                "tick": tick,
                "source_phase": model.states[source],
                "source_target": target[source],
                "source_verified_correct": verified_source,
                "errors": current_errors,
                "syndrome_rows": list(rows),
                "syndrome_columns": list(cols),
                "raw_matchings": raw,
                "history_compatible_matchings": compatible,
                "surviving_matches_actual_errors": (
                    len(compatible) == 1 and compatible[0] == current_errors
                ),
                "protected_targets": {
                    str(index): endpoint
                    for index, endpoint in model.protected_targets.items()
                },
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
    )[:8]
    target = targets[TARGET_INDEX]
    indices = _noise_indices(SEED, TARGET_INDEX, WIDTH * HEIGHT, TRIALS_PER_TARGET)

    rows = []
    for case in CASES:
        trial_index = case["trial_index"]
        source = indices[trial_index]
        if source != case["expected_source"]:
            raise AssertionError(
                f"frozen source changed: expected {case['expected_source']}, got {source}"
            )
        model, timeline = _replay_case(target, source, config, hierarchy, mirror_law)
        post_source = timeline[1]
        if post_source["errors"] != case["expected_errors"]:
            raise AssertionError(
                f"frozen residual changed: expected {case['expected_errors']}, got {post_source['errors']}"
            )
        rows.append(
            {
                "trial_index": trial_index,
                "source": source,
                "expected_errors": case["expected_errors"],
                "timeline": timeline,
                "raw_two_matchings_at_tick2": len(post_source["raw_matchings"]) == 2,
                "source_verified_at_tick2": post_source["source_verified_correct"],
                "exactly_one_history_compatible_matching": len(
                    post_source["history_compatible_matchings"]
                ) == 1,
                "surviving_matching_equals_actual_errors": post_source[
                    "surviving_matches_actual_errors"
                ],
                "alternative_matching_contains_source": (
                    len(post_source["raw_matchings"]) == 2
                    and any(source in matching for matching in post_source["raw_matchings"])
                ),
            }
        )

    summary = {
        "cases": len(rows),
        "raw_two_matchings": sum(r["raw_two_matchings_at_tick2"] for r in rows),
        "source_verified": sum(r["source_verified_at_tick2"] for r in rows),
        "unique_after_history_filter": sum(
            r["exactly_one_history_compatible_matching"] for r in rows
        ),
        "surviving_equals_actual": sum(
            r["surviving_matching_equals_actual_errors"] for r in rows
        ),
        "alternative_contains_source": sum(
            r["alternative_matching_contains_source"] for r in rows
        ),
    }
    hypothesis_confirmed = all(
        r["raw_two_matchings_at_tick2"]
        and r["source_verified_at_tick2"]
        and r["exactly_one_history_compatible_matching"]
        and r["surviving_matching_equals_actual_errors"]
        and r["alternative_matching_contains_source"]
        for r in rows
    )
    report = {
        "schema": "cosmic-organics/w82-history-disambiguation-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_pr": 38,
        "rows": rows,
        "summary": summary,
        "hypothesis_confirmed": hypothesis_confirmed,
        "decision_contract": (
            "if both residuals have two raw parity matchings and verified repair "
            "history excludes exactly the false matching while the survivor equals "
            "the actual residual pair, a history-aware two-error decoder is justified "
            "for the next development experiment"
        ),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if not hypothesis_confirmed:
        raise SystemExit("repair-history disambiguation hypothesis not confirmed")


if __name__ == "__main__":
    main()
