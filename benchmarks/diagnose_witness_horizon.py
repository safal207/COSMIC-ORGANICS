"""Diagnostic-only horizon map for MORPHOS-W2 persistent witness intent.

This script does not select parameters and does not alter the original W2
6-step gates. It asks whether residual W2 failures are a capability failure or
an evaluation-horizon/latency effect by replaying the same development corpora
at several fixed horizons.
"""
from __future__ import annotations

import json

from benchmarks.probe_witness_persistent import (
    CORPORA,
    MAX_TARGETS,
    TRIALS_PER_TARGET,
    WITNESS_COMMIT_DELAY,
    WITNESS_DRIVE,
    _corrupt_all,
    _manifest,
)
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.multimirror import MultiReflectiveGrid2D
from morphos.witness import IndependentWitnessGrid2D, WitnessLaw
from morphos.witness_persistent import PersistentWitnessGrid2D

HORIZONS = [2, 4, 6, 8, 10, 12, 16]
TARGET_DISCOVERY_STEPS = 6


def _hamming(left: str, right: str) -> int:
    return sum(a != b for a, b in zip(left, right))


def _run_model(cls, target, index, config, hierarchy, m2_law, horizon):
    if cls is MultiReflectiveGrid2D:
        model = cls(target, config=config, law=hierarchy, reflective_law=m2_law)
    else:
        model = cls(
            target,
            config=config,
            law=hierarchy,
            reflective_law=m2_law,
            witness_law=WitnessLaw(
                witness_drive=WITNESS_DRIVE,
                commit_delay=WITNESS_COMMIT_DELAY,
            ),
        )
    _corrupt_all(model, index)
    model.run([0.0] * horizon)
    return model


def _corpus(spec: dict) -> dict:
    manifest = _manifest()
    width = spec["width"]
    height = spec["height"]
    config, hierarchy = _s2_components(manifest, width, height)
    m2_law = _m2_law(manifest)
    seeds = _sha_binary_seeds(spec["seed"], spec["samples"], width * height)
    targets = _fixed_binary_targets(
        seeds, config, hierarchy, TARGET_DISCOVERY_STEPS
    )[:MAX_TARGETS]
    if not targets:
        raise RuntimeError("diagnostic corpus produced no binary fixed targets")

    rows = []
    for horizon in HORIZONS:
        counts = {
            "m2_exact": 0,
            "w1_exact": 0,
            "w2_exact": 0,
            "w2_source_repaired": 0,
            "w2_active_latch": 0,
            "w2_latch_cleared": 0,
        }
        w2_residual_hamming = 0
        trials = 0

        for target_index, target in enumerate(targets):
            indices = _noise_indices(
                spec["seed"], target_index, width * height, TRIALS_PER_TARGET
            )
            for index in indices:
                m2 = _run_model(
                    MultiReflectiveGrid2D,
                    target,
                    index,
                    config,
                    hierarchy,
                    m2_law,
                    horizon,
                )
                w1 = _run_model(
                    IndependentWitnessGrid2D,
                    target,
                    index,
                    config,
                    hierarchy,
                    m2_law,
                    horizon,
                )
                w2 = _run_model(
                    PersistentWitnessGrid2D,
                    target,
                    index,
                    config,
                    hierarchy,
                    m2_law,
                    horizon,
                )

                m2_final = m2.state_string()
                w1_final = w1.state_string()
                w2_final = w2.state_string()
                counts["m2_exact"] += int(m2_final == target)
                counts["w1_exact"] += int(w1_final == target)
                counts["w2_exact"] += int(w2_final == target)
                counts["w2_source_repaired"] += int(w2_final[index] == target[index])
                counts["w2_active_latch"] += int(w2.latched_index is not None)
                counts["w2_latch_cleared"] += int(w2.latch_clear_events > 0)
                w2_residual_hamming += _hamming(w2_final, target)
                trials += 1

        rate = lambda key: counts[key] / trials
        rows.append({
            "horizon": horizon,
            "trials": trials,
            "m2_exact": rate("m2_exact"),
            "w1_exact": rate("w1_exact"),
            "w2_exact": rate("w2_exact"),
            "w2_gain_vs_m2": rate("w2_exact") - rate("m2_exact"),
            "w2_gain_vs_w1": rate("w2_exact") - rate("w1_exact"),
            "w2_source_repaired": rate("w2_source_repaired"),
            "w2_active_latch": rate("w2_active_latch"),
            "w2_latch_cleared": rate("w2_latch_cleared"),
            "w2_mean_residual_hamming": w2_residual_hamming / trials,
        })

    return {
        "width": width,
        "height": height,
        "seed": spec["seed"],
        "rows": rows,
    }


def main() -> None:
    corpora = [_corpus(spec) for spec in CORPORA]

    by_horizon = []
    for horizon in HORIZONS:
        selected = [
            next(row for row in corpus["rows"] if row["horizon"] == horizon)
            for corpus in corpora
        ]
        by_horizon.append({
            "horizon": horizon,
            "minimum_w2_exact": min(row["w2_exact"] for row in selected),
            "minimum_w2_gain_vs_m2": min(row["w2_gain_vs_m2"] for row in selected),
            "minimum_w2_gain_vs_w1": min(row["w2_gain_vs_w1"] for row in selected),
            "minimum_w2_source_repaired": min(
                row["w2_source_repaired"] for row in selected
            ),
            "maximum_w2_active_latch": max(
                row["w2_active_latch"] for row in selected
            ),
            "maximum_w2_mean_residual_hamming": max(
                row["w2_mean_residual_hamming"] for row in selected
            ),
            "original_25pp_gain_gate_would_be_met_at_this_horizon": all(
                row["w2_gain_vs_m2"] >= 0.25 for row in selected
            ),
        })

    print(json.dumps({
        "diagnostic_only": True,
        "reuses_w2_development_corpora": True,
        "changes_original_w2_gate": False,
        "frozen_witness_drive": WITNESS_DRIVE,
        "horizons": HORIZONS,
        "corpora": corpora,
        "summary_by_horizon": by_horizon,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
