"""Diagnostic-only classification of residual failures after frozen W7 confirmation.

This replays the nine already-frozen W7 confirmation corpora without changing
any mechanism, coefficient, threshold, decoder, horizon, or gate. The goal is
to identify the first remaining divergence inside the existing single-bit
common-mode contract before proposing W8.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.probe_witness_repair_set import _return_handoffs
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.witness import WitnessLaw
from morphos.witness_repair_set import RepairSetAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w7_confirmation_manifest.json")


def _errors(model, target: str) -> list[int]:
    return [
        index
        for index, (actual, expected) in enumerate(zip(model.states, target))
        if actual != expected
    ]


def _snapshot(model, target: str, source: int, tick: int) -> dict:
    errors = _errors(model, target)
    syndrome = model.syndrome()
    localized = model.localized_error_index()
    return {
        "tick": tick,
        "errors": errors,
        "error_phases": {str(i): model.states[i] for i in errors},
        "source_correct": model.states[source] == target[source],
        "mixed_indices": [i for i, phase in enumerate(model.states) if phase == "M"],
        "syndrome_rows": list(syndrome[0]),
        "syndrome_columns": list(syndrome[1]),
        "localized": localized,
        "fence_active": model.selective_fence_active,
        "latched_index": model.latched_index,
        "protected_targets": {str(k): v for k, v in model.protected_targets.items()},
        "handoff_events": model.handoff_events,
        "erasure_handoff_events": model.erasure_handoff_events,
        "return_handoffs": _return_handoffs(model.handoff_history),
        "exact": not errors,
    }


def _classify(at8: dict, at12: dict, source: int) -> str:
    if at8["exact"]:
        return "success_at_8"
    if at12["exact"]:
        return "late_recovery_by_12"

    errors = at12["errors"]
    if source in errors:
        return "source_not_repaired"
    if len(errors) == 1 and at12["error_phases"].get(str(errors[0])) == "M":
        return "single_m_residual"
    if len(errors) == 1 and at12["localized"] == errors[0]:
        return "single_binary_unique_residual"
    if len(errors) > 1 and at12["localized"] is None:
        return "multi_error_ambiguous"
    if at12["return_handoffs"] > 0:
        return "handoff_recurrence"
    return "other_residual"


def _run_trial(*, target: str, source: int, config, hierarchy, mirror_law, protocol: dict) -> dict:
    model = RepairSetAuthorityGrid2D(
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
    at8 = None
    at12 = None
    first_source_correct_tick = None
    first_exact_tick = None
    max_error_count = 0
    max_mixed_count = 0

    for tick in range(1, protocol["retention_horizon"] + 1):
        model.step(0.0)
        snap = _snapshot(model, target, source, tick)
        max_error_count = max(max_error_count, len(snap["errors"]))
        max_mixed_count = max(max_mixed_count, len(snap["mixed_indices"]))
        if first_source_correct_tick is None and snap["source_correct"]:
            first_source_correct_tick = tick
        if first_exact_tick is None and snap["exact"]:
            first_exact_tick = tick
        if tick == protocol["evaluation_horizon"]:
            at8 = snap
        if tick == protocol["retention_horizon"]:
            at12 = snap

    assert at8 is not None and at12 is not None
    category = _classify(at8, at12, source)
    return {
        "category": category,
        "source": source,
        "source_anchor": model._is_anchor(source),
        "source_domain": list(model._domain(source)),
        "source_target_phase": target[source],
        "first_source_correct_tick": first_source_correct_tick,
        "first_exact_tick": first_exact_tick,
        "max_error_count": max_error_count,
        "max_mixed_count": max_mixed_count,
        "at8": at8,
        "at12": at12,
        "handoff_history": [list(pair) for pair in model.handoff_history],
        "max_repair_set_size": model.max_repair_set_size,
    }


def run_diagnostic() -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    rows = []
    by_corpus = []

    for spec in protocol["confirmation_corpora"]:
        width, height = spec["width"], spec["height"]
        cells = width * height
        config, hierarchy = _s2_components(base, width, height)
        mirror_law = _m2_law(base)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(spec["seed"], spec["samples"], cells),
            config,
            hierarchy,
            protocol["target_discovery_steps"],
        )[: protocol["max_targets"]]

        corpus_rows = []
        for target_index, target in enumerate(targets):
            indices = _noise_indices(
                spec["seed"], target_index, cells, protocol["trials_per_target"]
            )
            for trial_index, source in enumerate(indices):
                row = _run_trial(
                    target=target,
                    source=source,
                    config=config,
                    hierarchy=hierarchy,
                    mirror_law=mirror_law,
                    protocol=protocol,
                )
                row.update(
                    {
                        "width": width,
                        "height": height,
                        "seed": spec["seed"],
                        "target_index": target_index,
                        "trial_index": trial_index,
                    }
                )
                rows.append(row)
                corpus_rows.append(row)

        counts = Counter(row["category"] for row in corpus_rows)
        by_corpus.append(
            {
                "width": width,
                "height": height,
                "seed": spec["seed"],
                "trials": len(corpus_rows),
                "category_counts": dict(sorted(counts.items())),
                "recovery_at_8": sum(row["at8"]["exact"] for row in corpus_rows) / len(corpus_rows),
                "recovery_at_12": sum(row["at12"]["exact"] for row in corpus_rows) / len(corpus_rows),
            }
        )

    residual = [row for row in rows if not row["at8"]["exact"]]
    persistent = [row for row in rows if not row["at12"]["exact"]]
    counts = Counter(row["category"] for row in rows)
    persistent_counts = Counter(row["category"] for row in persistent)
    by_size = defaultdict(Counter)
    for row in persistent:
        by_size[f'{row["width"]}x{row["height"]}'][row["category"]] += 1

    return {
        "schema": "cosmic-organics/w7-residual-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_confirmation_head": protocol["frozen_from_head"],
        "confirmation_head_replayed": "77e811ee91a2cc214ca3171f22ade9901a496705",
        "trial_count": len(rows),
        "failure_at_8_count": len(residual),
        "persistent_failure_at_12_count": len(persistent),
        "category_counts_all_trials": dict(sorted(counts.items())),
        "persistent_category_counts": dict(sorted(persistent_counts.items())),
        "persistent_by_size": {
            size: dict(sorted(counter.items())) for size, counter in sorted(by_size.items())
        },
        "by_corpus": by_corpus,
        "persistent_failures": persistent,
        "interpretation_contract": {
            "source_not_repaired": "the originally corrupted source is still wrong at tick 12",
            "single_m_residual": "source repairs but one known transition-state erasure remains",
            "single_binary_unique_residual": "source repairs and a single binary residual is independently localizable but unresolved",
            "multi_error_ambiguous": "more than one residual remains and the single-error witness cannot uniquely localize",
            "handoff_recurrence": "repair ownership returns to a prior owner after handoff",
            "late_recovery_by_12": "tick-8 miss closes under unchanged dynamics by tick 12",
        },
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
