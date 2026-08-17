"""Diagnostic-only decomposition of the MORPHOS-W4 9x9 confirmation margin.

This module does not tune W4 and does not change any confirmation gate. It
replays only the already-frozen 9x9 confirmation corpora and classifies each
single-bit trial by geometry, first-step corrective margin, target-cell repair,
collateral divergence, and fence/recommit timing.
"""
from __future__ import annotations

import json
from collections import defaultdict
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
from morphos.witness_fence import RecoveryFenceGrid2D
from morphos.witness_selective import SelectiveAuthorityGrid2D

_VALUE = {"A": 0.0, "M": 0.5, "C": 1.0}
_PROTOCOL = Path(__file__).with_name("w4_confirmation_manifest.json")


def _opposite(value: str) -> str:
    return "C" if value == "A" else "A"


def _bucket_inc(store: dict, name: str, key: str, success: bool) -> None:
    bucket = store.setdefault(name, {}).setdefault(key, {"trials": 0, "successes": 0})
    bucket["trials"] += 1
    bucket["successes"] += int(success)


def _finalize_buckets(store: dict) -> dict:
    result = {}
    for name, values in store.items():
        result[name] = {}
        for key, row in sorted(values.items()):
            result[name][key] = {
                **row,
                "recovery": row["successes"] / row["trials"],
            }
    return result


def _margin_bucket(value: float) -> str:
    if value < -1e-12:
        return "negative"
    if value < 0.05:
        return "0_to_0.05"
    if value < 0.15:
        return "0.05_to_0.15"
    return "ge_0.15"


def _trial(
    *,
    target: str,
    target_index: int,
    index: int,
    seed: int,
    config,
    hierarchy,
    m2_law,
    protocol: dict,
) -> dict:
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
    row, col = divmod(index, config.width)
    neighbors = model._neighbors(index)
    domain = model._domain(index)
    cross_domain_neighbors = sum(model._domain(n) != domain for n in neighbors)
    anchor = model._is_anchor(index)
    edge_class = (
        "corner"
        if row in (0, config.height - 1) and col in (0, config.width - 1)
        else "edge"
        if row in (0, config.height - 1) or col in (0, config.width - 1)
        else "interior"
    )

    original = target[index]
    corrupted = _opposite(original)
    correction_sign = 1.0 if original == "C" else -1.0
    coupling = config.anchor_coupling if anchor else config.adaptive_coupling
    threshold = config.anchor_threshold if anchor else config.adaptive_threshold
    intra_factor = hierarchy.intra_factor(config.width, config.height)
    weighted_delta = sum(
        (intra_factor if model._domain(n) == domain else 1.0)
        * (_VALUE[target[n]] - _VALUE[corrupted])
        for n in neighbors
    ) / len(neighbors)
    neighbor_drive = coupling * weighted_delta
    signed_neighbor_drive = correction_sign * neighbor_drive
    first_step_signed_drive = signed_neighbor_drive + protocol["witness_drive"]
    first_step_margin = first_step_signed_drive - threshold
    same_target_neighbors = sum(target[n] == original for n in neighbors)

    _corrupt_all(model, index)
    localized_before_run = model.localized_error_index() == index

    first_target_tick = None
    first_release_tick = None
    snap8 = None
    for tick in range(1, protocol["retention_horizon"] + 1):
        model.step(0.0)
        if first_target_tick is None and model.states[index] == original:
            first_target_tick = tick
        if first_release_tick is None and model.fence_release_events > 0:
            first_release_tick = tick
        if tick == protocol["evaluation_horizon"]:
            residual = [i for i, (a, b) in enumerate(zip(model.states, target)) if a != b]
            snap8 = {
                "exact": not residual,
                "target_cell_repaired": model.states[index] == original,
                "residual_hamming": len(residual),
                "collateral_hamming": sum(i != index for i in residual),
                "fence_active": model.selective_fence_active,
                "target_mirrors": [
                    model.local_mirror_states[index],
                    model.domain_mirror_states[index],
                    model.system_mirror_states[index],
                ],
                "all_target_mirrors_recommitted": all(
                    phase == original
                    for phase in (
                        model.local_mirror_states[index],
                        model.domain_mirror_states[index],
                        model.system_mirror_states[index],
                    )
                ),
            }

    assert snap8 is not None
    exact12 = model.state_string() == target

    w3 = RecoveryFenceGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=m2_law,
        witness_law=WitnessLaw(
            witness_drive=protocol["witness_drive"],
            commit_delay=protocol["witness_commit_delay"],
        ),
    )
    _corrupt_all(w3, index)
    w3.run([0.0] * protocol["evaluation_horizon"])

    if snap8["exact"]:
        failure_class = "success"
    elif not localized_before_run:
        failure_class = "localization_failure"
    elif not snap8["target_cell_repaired"]:
        failure_class = "target_cell_not_repaired"
    elif snap8["collateral_hamming"] > 0:
        failure_class = "target_repaired_collateral_divergence"
    elif snap8["fence_active"] or not snap8["all_target_mirrors_recommitted"]:
        failure_class = "target_repaired_recommit_incomplete"
    else:
        failure_class = "other"

    return {
        "seed": seed,
        "target_index": target_index,
        "index": index,
        "row": row,
        "col": col,
        "phase": original,
        "cell_class": "anchor" if anchor else "adaptive",
        "edge_class": edge_class,
        "domain": list(domain),
        "domain_mod": [row % hierarchy.domain_size, col % hierarchy.domain_size],
        "neighbor_count": len(neighbors),
        "cross_domain_neighbors": cross_domain_neighbors,
        "same_target_neighbors": same_target_neighbors,
        "signed_neighbor_drive_t0": signed_neighbor_drive,
        "first_step_signed_drive": first_step_signed_drive,
        "first_step_margin": first_step_margin,
        "margin_bucket": _margin_bucket(first_step_margin),
        "localized_before_run": localized_before_run,
        "first_target_tick": first_target_tick,
        "first_release_tick": first_release_tick,
        "w3_exact_8": w3.state_string() == target,
        "w4_exact_8": snap8["exact"],
        "w4_exact_12": exact12,
        "target_cell_repaired_8": snap8["target_cell_repaired"],
        "residual_hamming_8": snap8["residual_hamming"],
        "collateral_hamming_8": snap8["collateral_hamming"],
        "fence_active_8": snap8["fence_active"],
        "all_target_mirrors_recommitted_8": snap8["all_target_mirrors_recommitted"],
        "failure_class": failure_class,
    }


def run_diagnostic() -> dict:
    protocol = json.loads(_PROTOCOL.read_text(encoding="utf-8"))
    base_manifest = _manifest()
    specs = [
        spec
        for spec in protocol["confirmation_corpora"]
        if spec["width"] == 9 and spec["height"] == 9
    ]
    if len(specs) != 3:
        raise RuntimeError("expected exactly three frozen 9x9 confirmation corpora")

    all_trials = []
    seed_summaries = []
    global_buckets: dict = {}

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
        rows = []
        seed_buckets: dict = {}
        for target_index, target in enumerate(targets):
            indices = _noise_indices(
                spec["seed"], target_index, 81, protocol["trials_per_target"]
            )
            for index in indices:
                row = _trial(
                    target=target,
                    target_index=target_index,
                    index=index,
                    seed=spec["seed"],
                    config=config,
                    hierarchy=hierarchy,
                    m2_law=m2_law,
                    protocol=protocol,
                )
                rows.append(row)
                all_trials.append(row)
                success = row["w4_exact_8"]
                for name, key in (
                    ("cell_class", row["cell_class"]),
                    ("edge_class", row["edge_class"]),
                    ("cross_domain_neighbors", str(row["cross_domain_neighbors"])),
                    ("same_target_neighbors", str(row["same_target_neighbors"])),
                    ("margin_bucket", row["margin_bucket"]),
                    ("phase", row["phase"]),
                    ("domain_mod", f"{row['domain_mod'][0]},{row['domain_mod'][1]}"),
                ):
                    _bucket_inc(seed_buckets, name, key, success)
                    _bucket_inc(global_buckets, name, key, success)

        failures = [r for r in rows if not r["w4_exact_8"]]
        classes = defaultdict(int)
        for row in failures:
            classes[row["failure_class"]] += 1
        seed_summaries.append(
            {
                "seed": spec["seed"],
                "trials": len(rows),
                "recovery_8": sum(r["w4_exact_8"] for r in rows) / len(rows),
                "w3_recovery_8": sum(r["w3_exact_8"] for r in rows) / len(rows),
                "failures": len(failures),
                "failure_classes": dict(sorted(classes.items())),
                "mean_first_step_margin_success": (
                    sum(r["first_step_margin"] for r in rows if r["w4_exact_8"])
                    / max(1, sum(r["w4_exact_8"] for r in rows))
                ),
                "mean_first_step_margin_failure": (
                    sum(r["first_step_margin"] for r in failures) / max(1, len(failures))
                ),
                "buckets": _finalize_buckets(seed_buckets),
            }
        )

    failures = [r for r in all_trials if not r["w4_exact_8"]]
    classes = defaultdict(int)
    for row in failures:
        classes[row["failure_class"]] += 1

    failing_seed = 202608161023
    failing_seed_failures = [r for r in failures if r["seed"] == failing_seed]
    return {
        "schema": "cosmic-organics/w4-9x9-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "frozen_confirmation_head": protocol["frozen_from_head"],
        "analyzed_seeds": [spec["seed"] for spec in specs],
        "seed_summaries": seed_summaries,
        "global_summary": {
            "trials": len(all_trials),
            "failures": len(failures),
            "failure_classes": dict(sorted(classes.items())),
            "buckets": _finalize_buckets(global_buckets),
        },
        "failing_seed_202608161023_failure_details": failing_seed_failures,
        "interpretation_contract": {
            "localization_limited": "localization_failure dominates failures",
            "transition_limited": "target_cell_not_repaired dominates failures",
            "propagation_limited": "target_repaired_collateral_divergence dominates failures",
            "recommit_limited": "target_repaired_recommit_incomplete dominates failures",
            "geometry_signal": "failure rate materially clusters by anchor/domain/edge/margin buckets",
        },
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
