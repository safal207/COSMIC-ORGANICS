"""Classify the fresh W5 collateral-rescue confirmation boundary.

Diagnostic only. Replays the nine frozen W5 confirmation corpora and inspects
only trials that are W4 collateral failures: W4 is not exact at tick 8 while
the originally corrupted source cell is already correct.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import _fixed_binary_targets, _m2_law, _noise_indices, _s2_components, _sha_binary_seeds
from benchmarks.run_w4_confirmation import _run
from morphos.witness import WitnessLaw
from morphos.witness_handoff import HandoffAuthorityGrid2D
from morphos.witness_selective import SelectiveAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w5_confirmation_manifest.json")


def _errors(model, target: str) -> list[int]:
    return [i for i, (actual, expected) in enumerate(zip(model.states, target)) if actual != expected]


def _trace_w5(target, source, config, hierarchy, mirror_law, protocol):
    model = HandoffAuthorityGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(
            witness_drive=protocol["witness_drive"],
            commit_delay=protocol["witness_commit_delay"],
        ),
    )
    _corrupt_all(model, source)
    timeline = []
    first_source_correct = None
    first_other_unique_after_source_correct = None
    for tick in range(1, protocol["retention_horizon"] + 1):
        model.step(0.0)
        errors = _errors(model, target)
        localized = model.localized_error_index()
        source_correct = source not in errors
        if source_correct and first_source_correct is None:
            first_source_correct = tick
        if (
            source_correct
            and localized is not None
            and localized != source
            and first_other_unique_after_source_correct is None
        ):
            first_other_unique_after_source_correct = tick
        timeline.append({
            "tick": tick,
            "errors": errors,
            "localized": localized,
            "latched_index": model.latched_index,
            "latched_target": model.latched_target,
            "handoff_events": model.handoff_events,
            "protected_count": len(model.protected_targets),
            "fence_active": model.selective_fence_active,
        })
    at8 = timeline[protocol["evaluation_horizon"] - 1]
    at12 = timeline[protocol["retention_horizon"] - 1]
    return {
        "success_at_8": not at8["errors"],
        "success_at_12": not at12["errors"],
        "handoff_events": model.handoff_events,
        "handoff_history": [list(pair) for pair in model.handoff_history],
        "first_source_correct_tick": first_source_correct,
        "first_other_unique_after_source_correct_tick": first_other_unique_after_source_correct,
        "errors_at_8": at8["errors"],
        "errors_at_12": at12["errors"],
        "localized_at_8": at8["localized"],
        "localized_at_12": at12["localized"],
        "latched_at_8": at8["latched_index"],
        "latched_at_12": at12["latched_index"],
        "protected_count_at_12": at12["protected_count"],
        "timeline": timeline,
    }


def run_diagnostic() -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    rows = []
    by_size = defaultdict(Counter)

    for spec in protocol["confirmation_corpora"]:
        width, height = spec["width"], spec["height"]
        cells = width * height
        config, hierarchy = _s2_components(base, width, height)
        mirror_law = _m2_law(base)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(spec["seed"], spec["samples"], cells),
            config, hierarchy, protocol["target_discovery_steps"],
        )[: protocol["max_targets"]]
        for target_index, target in enumerate(targets):
            indices = _noise_indices(spec["seed"], target_index, cells, protocol["trials_per_target"])
            for trial_index, source in enumerate(indices):
                w4 = _run(
                    SelectiveAuthorityGrid2D, target, [source], config, hierarchy, mirror_law,
                    protocol["evaluation_horizon"], witness_drive=protocol["witness_drive"],
                    witness_commit_delay=protocol["witness_commit_delay"],
                )
                if w4.state_string() == target or w4.states[source] != target[source]:
                    continue
                trace = _trace_w5(target, source, config, hierarchy, mirror_law, protocol)
                if trace["success_at_8"]:
                    category = "handoff_then_recovered" if trace["handoff_events"] else "recovered_without_handoff"
                elif trace["handoff_events"]:
                    category = "handoff_but_failed"
                else:
                    category = "no_handoff"
                by_size[f"{width}x{height}"][category] += 1
                rows.append({
                    "width": width,
                    "height": height,
                    "seed": spec["seed"],
                    "target_index": target_index,
                    "trial_index": trial_index,
                    "source": source,
                    "source_anchor": w4._is_anchor(source),
                    "category": category,
                    **{k: v for k, v in trace.items() if k != "timeline"},
                })

    counts = Counter(row["category"] for row in rows)
    unresolved = [row for row in rows if not row["success_at_8"]]
    no_handoff = [row for row in unresolved if row["category"] == "no_handoff"]
    handed_failed = [row for row in unresolved if row["category"] == "handoff_but_failed"]
    return {
        "schema": "cosmic-organics/w5-collateral-boundary-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_confirmation_head": "5436f9bdc8ba5dc47587c5360914555e0af3bc84",
        "w4_collateral_trials": len(rows),
        "category_counts": dict(sorted(counts.items())),
        "unresolved_count": len(unresolved),
        "no_handoff_count": len(no_handoff),
        "handoff_but_failed_count": len(handed_failed),
        "no_handoff_with_unique_other_after_source_correct_count": sum(
            row["first_other_unique_after_source_correct_tick"] is not None for row in no_handoff
        ),
        "handoff_but_failed_still_unresolved_at_12_count": sum(not row["success_at_12"] for row in handed_failed),
        "by_size": {size: dict(sorted(counter.items())) for size, counter in sorted(by_size.items())},
        "unresolved": unresolved,
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
