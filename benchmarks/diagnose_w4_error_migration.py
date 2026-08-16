"""Trace error migration in the frozen W4 9x9 confirmation failures.

Diagnostic only: no mechanism, amplitude, horizon, or gate is changed.
The question is whether W4 repairs the originally localized cell while the
remaining parity syndrome moves to a different cell but the repair latch keeps
ownership of the old cell.
"""
from __future__ import annotations

import json
from collections import Counter

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from benchmarks.run_w4_confirmation import _load_protocol
from morphos.witness import WitnessLaw
from morphos.witness_selective import SelectiveAuthorityGrid2D


def _errors(model: SelectiveAuthorityGrid2D, target: str) -> list[int]:
    return [i for i, (actual, expected) in enumerate(zip(model.states, target)) if actual != expected]


def _relation(model: SelectiveAuthorityGrid2D, source: int, other: int) -> dict:
    width = model.config.width
    sr, sc = divmod(source, width)
    rr, rc = divmod(other, width)
    return {
        "index": other,
        "row": rr,
        "col": rc,
        "manhattan_from_source": abs(sr - rr) + abs(sc - rc),
        "is_direct_neighbor": other in model._neighbors(source),
        "same_domain": model._domain(source) == model._domain(other),
        "source_domain": list(model._domain(source)),
        "other_domain": list(model._domain(other)),
        "other_anchor": model._is_anchor(other),
        "other_domain_local_row": rr % model.law.domain_size,
        "other_domain_local_col": rc % model.law.domain_size,
        "other_target_phase": None,
    }


def _trace(target: str, source: int, config, hierarchy, reflective_law, protocol: dict) -> dict:
    model = SelectiveAuthorityGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=reflective_law,
        witness_law=WitnessLaw(
            witness_drive=protocol["witness_drive"],
            commit_delay=protocol["witness_commit_delay"],
        ),
    )
    _corrupt_all(model, source)

    initial_latched = None
    first_source_correct_tick = None
    first_collateral_tick = None
    first_migrated_localization_tick = None
    first_migrated_localized_index = None
    trace = []

    for tick in range(1, protocol["retention_horizon"] + 1):
        model.step(0.0)
        errors = _errors(model, target)
        localized = model.localized_error_index()
        latched = model.latched_index
        if initial_latched is None and latched is not None:
            initial_latched = latched
        source_correct = source not in errors
        collateral = [idx for idx in errors if idx != source]
        if source_correct and first_source_correct_tick is None:
            first_source_correct_tick = tick
        if collateral and first_collateral_tick is None:
            first_collateral_tick = tick
        if (
            localized is not None
            and latched is not None
            and localized != latched
            and first_migrated_localization_tick is None
        ):
            first_migrated_localization_tick = tick
            first_migrated_localized_index = localized
        trace.append(
            {
                "tick": tick,
                "errors": errors,
                "localized_error_index": localized,
                "latched_index": latched,
                "latched_target": model.latched_target,
                "source_correct": source_correct,
                "fence_active": model.selective_fence_active,
                "syndrome": [list(model.syndrome()[0]), list(model.syndrome()[1])],
            }
        )

    final_errors = trace[protocol["evaluation_horizon"] - 1]["errors"]
    collateral_at_8 = [idx for idx in final_errors if idx != source]
    collateral = None
    if len(collateral_at_8) == 1:
        collateral = _relation(model, source, collateral_at_8[0])
        collateral["other_target_phase"] = target[collateral_at_8[0]]

    stale_ticks = [
        row["tick"]
        for row in trace
        if row["localized_error_index"] is not None
        and row["latched_index"] is not None
        and row["localized_error_index"] != row["latched_index"]
    ]
    return {
        "source_index": source,
        "source_anchor": model._is_anchor(source),
        "source_target_phase": target[source],
        "initial_latched_index": initial_latched,
        "success_at_8": len(final_errors) == 0,
        "final_errors_at_8": final_errors,
        "source_correct_at_8": source not in final_errors,
        "collateral_at_8": collateral,
        "first_source_correct_tick": first_source_correct_tick,
        "first_collateral_tick": first_collateral_tick,
        "first_migrated_localization_tick": first_migrated_localization_tick,
        "first_migrated_localized_index": first_migrated_localized_index,
        "stale_latch_tick_count": len(stale_ticks),
        "stale_latch_ticks": stale_ticks,
        "trace": trace,
    }


def run_diagnostic() -> dict:
    protocol = _load_protocol()
    spec = next(
        row for row in protocol["confirmation_corpora"]
        if row["width"] == 9 and row["height"] == 9 and row["seed"] == 202608161023
    )
    base_manifest = _manifest()
    config, hierarchy = _s2_components(base_manifest, 9, 9)
    reflective_law = _m2_law(base_manifest)
    cells = 81
    targets = _fixed_binary_targets(
        _sha_binary_seeds(spec["seed"], spec["samples"], cells),
        config,
        hierarchy,
        protocol["target_discovery_steps"],
    )[: protocol["max_targets"]]

    rows = []
    for target_index, target in enumerate(targets):
        indices = _noise_indices(spec["seed"], target_index, cells, protocol["trials_per_target"])
        for trial_index, source in enumerate(indices):
            row = _trace(target, source, config, hierarchy, reflective_law, protocol)
            row["target_index"] = target_index
            row["trial_index"] = trial_index
            rows.append(row)

    failures = [row for row in rows if not row["success_at_8"]]
    collateral_failures = [row for row in failures if row["source_correct_at_8"]]
    source_failures = [row for row in failures if not row["source_correct_at_8"]]
    migrated = [row for row in collateral_failures if row["first_migrated_localization_tick"] is not None]

    relation_counts = Counter()
    for row in collateral_failures:
        rel = row["collateral_at_8"]
        if rel:
            relation_counts[(rel["manhattan_from_source"], rel["is_direct_neighbor"], rel["same_domain"])] += 1

    compact = []
    for row in failures:
        compact.append(
            {
                key: row[key]
                for key in (
                    "target_index",
                    "trial_index",
                    "source_index",
                    "source_anchor",
                    "source_target_phase",
                    "source_correct_at_8",
                    "final_errors_at_8",
                    "collateral_at_8",
                    "first_source_correct_tick",
                    "first_collateral_tick",
                    "first_migrated_localization_tick",
                    "first_migrated_localized_index",
                    "initial_latched_index",
                    "stale_latch_tick_count",
                    "stale_latch_ticks",
                )
            }
        )

    return {
        "schema": "cosmic-organics/w4-error-migration-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_confirmation_head": "b528a25f5e3c34fa1983f02219742f8607dca9f2",
        "corpus_seed": spec["seed"],
        "trial_count": len(rows),
        "failure_count": len(failures),
        "source_not_repaired_failure_count": len(source_failures),
        "source_repaired_but_collateral_failure_count": len(collateral_failures),
        "collateral_failure_with_migrated_unique_syndrome_count": len(migrated),
        "collateral_failure_migrated_unique_syndrome_fraction": (
            len(migrated) / len(collateral_failures) if collateral_failures else 0.0
        ),
        "relation_counts": [
            {
                "manhattan": signature[0],
                "direct_neighbor": signature[1],
                "same_domain": signature[2],
                "count": count,
            }
            for signature, count in relation_counts.most_common()
        ],
        "failures": compact,
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
