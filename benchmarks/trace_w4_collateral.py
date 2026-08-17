"""Trace W4 collateral failures without retuning or changing the mechanism.

The trace asks a narrow causal question: after W4 repairs the originally
localized cell, can a secondary fault become independently localizable while
the original selective repair transaction is still open? If so, W4 currently
cannot hand authority to that new syndrome because only one latched repair
transaction can be active at a time.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.witness import WitnessLaw
from morphos.witness_selective import SelectiveAuthorityGrid2D

_PROTOCOL = Path(__file__).with_name("w4_confirmation_manifest.json")


def _manhattan(a: int, b: int, width: int) -> int:
    ar, ac = divmod(a, width)
    br, bc = divmod(b, width)
    return abs(ar - br) + abs(ac - bc)


def _counter_dict(values) -> dict[str, int]:
    """Return a deterministically sorted JSON-safe histogram, including None."""
    counts = Counter("none" if value is None else str(value) for value in values)
    return dict(sorted(counts.items()))


def _trace_trial(*, target: str, target_index: int, index: int, seed: int, config, hierarchy, m2_law, protocol: dict) -> dict:
    model = SelectiveAuthorityGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=m2_law,
        witness_law=WitnessLaw(
            witness_drive=protocol["witness_drive"],
            commit_delay=protocol["witness_commit_delay"],
        ),
    )
    original_phase = target[index]
    original_domain = model._domain(index)
    _corrupt_all(model, index)

    timeline = []
    first_target_repair_tick = None
    first_collateral_tick = None
    first_binary_collateral_tick = None
    first_blocked_handoff_tick = None
    first_blocked_handoff_index = None
    first_new_localization_tick = None
    first_new_localization_index = None
    max_mismatches = 0
    max_binary_mismatches = 0

    for tick in range(1, protocol["retention_horizon"] + 1):
        model.step(0.0)
        mismatches = [i for i, (actual, expected) in enumerate(zip(model.states, target)) if actual != expected]
        binary_mismatches = [
            i
            for i in mismatches
            if model.states[i] in ("A", "C")
        ]
        mixed = [i for i, value in enumerate(model.states) if value == "M"]
        collateral = [i for i in mismatches if i != index]
        binary_collateral = [i for i in binary_mismatches if i != index]
        syndrome = model.syndrome()
        localized = model.localized_error_index()

        max_mismatches = max(max_mismatches, len(mismatches))
        max_binary_mismatches = max(max_binary_mismatches, len(binary_mismatches))

        if first_target_repair_tick is None and model.states[index] == original_phase:
            first_target_repair_tick = tick
        if first_collateral_tick is None and collateral:
            first_collateral_tick = tick
        if first_binary_collateral_tick is None and binary_collateral:
            first_binary_collateral_tick = tick
        if localized is not None and localized != index and first_new_localization_tick is None:
            first_new_localization_tick = tick
            first_new_localization_index = localized
        if (
            model.states[index] == original_phase
            and model.selective_fence_active
            and localized is not None
            and localized != index
            and first_blocked_handoff_tick is None
        ):
            first_blocked_handoff_tick = tick
            first_blocked_handoff_index = localized

        timeline.append(
            {
                "tick": tick,
                "target_phase": model.states[index],
                "mismatch_count": len(mismatches),
                "binary_mismatch_count": len(binary_mismatches),
                "mixed_count": len(mixed),
                "collateral_indices": collateral,
                "binary_collateral_indices": binary_collateral,
                "syndrome_rows": list(syndrome[0]),
                "syndrome_columns": list(syndrome[1]),
                "localized_index": localized,
                "latched_index": model.latched_index,
                "fence_active": model.selective_fence_active,
                "target_mirrors_agree": (
                    model.local_mirror_states[index] == original_phase
                    and model.domain_mirror_states[index] == original_phase
                    and model.system_mirror_states[index] == original_phase
                ),
            }
        )

    final_mismatches = [i for i, (actual, expected) in enumerate(zip(model.states, target)) if actual != expected]
    final_collateral = [i for i in final_mismatches if i != index]
    target_repaired = model.states[index] == original_phase
    exact = not final_mismatches
    collateral_failure = (not exact) and target_repaired and bool(final_collateral)

    relation = None
    if collateral_failure:
        collateral_index = final_collateral[0]
        relation = {
            "final_collateral_index": collateral_index,
            "manhattan_distance": _manhattan(index, collateral_index, config.width),
            "direct_neighbor": collateral_index in model._neighbors(index),
            "same_domain": model._domain(collateral_index) == original_domain,
            "target_cell_class": "anchor" if model._is_anchor(index) else "adaptive",
            "collateral_cell_class": "anchor" if model._is_anchor(collateral_index) else "adaptive",
            "target_domain": list(original_domain),
            "collateral_domain": list(model._domain(collateral_index)),
        }

    return {
        "seed": seed,
        "target_index": target_index,
        "corrupted_index": index,
        "exact_12": exact,
        "target_repaired_12": target_repaired,
        "collateral_failure_12": collateral_failure,
        "final_mismatches": final_mismatches,
        "first_target_repair_tick": first_target_repair_tick,
        "first_collateral_tick": first_collateral_tick,
        "first_binary_collateral_tick": first_binary_collateral_tick,
        "first_new_localization_tick": first_new_localization_tick,
        "first_new_localization_index": first_new_localization_index,
        "first_blocked_handoff_tick": first_blocked_handoff_tick,
        "first_blocked_handoff_index": first_blocked_handoff_index,
        "blocked_handoff_observed": first_blocked_handoff_tick is not None,
        "max_mismatches": max_mismatches,
        "max_binary_mismatches": max_binary_mismatches,
        "relation": relation,
        "timeline": timeline if collateral_failure else [],
    }


def run_trace() -> dict:
    protocol = json.loads(_PROTOCOL.read_text(encoding="utf-8"))
    base_manifest = _manifest()
    specs = [
        spec for spec in protocol["confirmation_corpora"]
        if spec["width"] == 9 and spec["height"] == 9
    ]

    traces = []
    for spec in specs:
        config, hierarchy = _s2_components(base_manifest, 9, 9)
        m2_law = _m2_law(base_manifest)
        seeds = _sha_binary_seeds(spec["seed"], spec["samples"], 81)
        targets = _fixed_binary_targets(
            seeds,
            config,
            hierarchy,
            protocol["target_discovery_steps"],
        )[: protocol["max_targets"]]
        for target_index, target in enumerate(targets):
            for index in _noise_indices(spec["seed"], target_index, 81, protocol["trials_per_target"]):
                trace = _trace_trial(
                    target=target,
                    target_index=target_index,
                    index=index,
                    seed=spec["seed"],
                    config=config,
                    hierarchy=hierarchy,
                    m2_law=m2_law,
                    protocol=protocol,
                )
                if trace["collateral_failure_12"]:
                    traces.append(trace)

    by_seed = {}
    for seed in sorted({row["seed"] for row in traces}):
        rows = [row for row in traces if row["seed"] == seed]
        by_seed[str(seed)] = {
            "collateral_failures": len(rows),
            "blocked_handoff_count": sum(row["blocked_handoff_observed"] for row in rows),
            "direct_neighbor_count": sum(row["relation"]["direct_neighbor"] for row in rows),
            "same_domain_count": sum(row["relation"]["same_domain"] for row in rows),
            "first_collateral_tick_counts": _counter_dict(row["first_collateral_tick"] for row in rows),
            "first_binary_collateral_tick_counts": _counter_dict(row["first_binary_collateral_tick"] for row in rows),
            "max_binary_mismatch_counts": _counter_dict(row["max_binary_mismatches"] for row in rows),
        }

    return {
        "schema": "cosmic-organics/w4-collateral-trace-0.1",
        "diagnostic_only_no_retuning": True,
        "hypothesis_under_test": "secondary fault appears during an open single-error repair transaction and becomes independently localizable, but W4 cannot hand off while the original fence remains active",
        "summary": {
            "collateral_failures": len(traces),
            "blocked_handoff_count": sum(row["blocked_handoff_observed"] for row in traces),
            "new_localization_after_original_count": sum(row["first_new_localization_tick"] is not None for row in traces),
            "direct_neighbor_count": sum(row["relation"]["direct_neighbor"] for row in traces),
            "same_domain_count": sum(row["relation"]["same_domain"] for row in traces),
            "all_target_repaired_before_or_at_final": all(row["target_repaired_12"] for row in traces),
        },
        "by_seed": by_seed,
        "traces": traces,
    }


def main() -> None:
    print(json.dumps(run_trace(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
