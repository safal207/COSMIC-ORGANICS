"""Development probe for MORPHOS-W2 persistent witness intent.

W2 freezes the smallest active W1 drive (0.25) and changes only one causal
mechanism: once parity localizes a one-bit error, the intended binary endpoint
is latched across the mandatory M phase until reached.

The recovery gates below were predeclared before the first W2 run. Additional
residual-error metrics are diagnostic only: they do not change those gates.
"""
from __future__ import annotations

import json

from benchmarks.run_multimirror import (
    DEFAULT_MANIFEST,
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.multimirror import MultiReflectiveGrid2D
from morphos.witness import IndependentWitnessGrid2D, WitnessLaw
from morphos.witness_persistent import PersistentWitnessGrid2D

CORPORA = [
    {"width": 5, "height": 5, "seed": 202608156001, "samples": 96},
    {"width": 7, "height": 7, "seed": 202608156011, "samples": 96},
    {"width": 9, "height": 9, "seed": 202608156021, "samples": 72},
]
RELAX_STEPS = 6
MAX_TARGETS = 12
TRIALS_PER_TARGET = 8
WITNESS_DRIVE = 0.25
WITNESS_COMMIT_DELAY = 8

# Predeclared before observing the first W2 development probe.
MIN_COMMON_GAIN_VS_M2 = 0.25
MIN_GAIN_VS_W1 = 0.10
MIN_PRIMARY_GAIN_VS_M2 = 0.0
MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED = 0.10


def _manifest():
    return json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))


def _corrupt_all(model, index: int) -> None:
    model.perturb_primary([index])
    model.perturb_local_mirror([index])
    model.perturb_domain_mirror([index])
    model.perturb_system_mirror([index])


def _hamming(left: str, right: str) -> int:
    return sum(a != b for a, b in zip(left, right))


def _corpus(spec: dict) -> dict:
    manifest = _manifest()
    width = spec["width"]
    height = spec["height"]
    config, hierarchy = _s2_components(manifest, width, height)
    m2_law = _m2_law(manifest)
    seeds = _sha_binary_seeds(spec["seed"], spec["samples"], width * height)
    targets = _fixed_binary_targets(seeds, config, hierarchy, RELAX_STEPS)[:MAX_TARGETS]
    if not targets:
        raise RuntimeError("development corpus produced no binary fixed targets")

    counts = {
        "m2_primary": 0,
        "w2_primary": 0,
        "m2_common": 0,
        "w1_common": 0,
        "w2_common": 0,
        "w2_corrupt_witness": 0,
        "w2_zero": 0,
    }
    latch_trials = 0
    latch_clear_trials = 0
    target_cell_repaired = 0
    collateral_failure_trials = 0
    residual_hamming_total = 0
    failed_residual_hamming_total = 0
    failed_trials = 0
    trials = 0

    for target_index, target in enumerate(targets):
        indices = _noise_indices(spec["seed"], target_index, width * height, TRIALS_PER_TARGET)
        for index in indices:
            def make_m2(common: bool):
                model = MultiReflectiveGrid2D(
                    target, config=config, law=hierarchy, reflective_law=m2_law
                )
                if common:
                    _corrupt_all(model, index)
                else:
                    model.perturb_primary([index])
                model.run([0.0] * RELAX_STEPS)
                return model

            def make_w1(common: bool):
                model = IndependentWitnessGrid2D(
                    target,
                    config=config,
                    law=hierarchy,
                    reflective_law=m2_law,
                    witness_law=WitnessLaw(
                        witness_drive=WITNESS_DRIVE,
                        commit_delay=WITNESS_COMMIT_DELAY,
                    ),
                )
                if common:
                    _corrupt_all(model, index)
                else:
                    model.perturb_primary([index])
                model.run([0.0] * RELAX_STEPS)
                return model

            def make_w2(common: bool, *, corrupt_witness: bool = False, zero: bool = False):
                model = PersistentWitnessGrid2D(
                    target,
                    config=config,
                    law=hierarchy,
                    reflective_law=m2_law,
                    witness_law=WitnessLaw(
                        witness_drive=0.0 if zero else WITNESS_DRIVE,
                        commit_delay=WITNESS_COMMIT_DELAY,
                    ),
                )
                if common:
                    _corrupt_all(model, index)
                else:
                    model.perturb_primary([index])
                if corrupt_witness:
                    model.perturb_witness_for_cell(index)
                model.run([0.0] * RELAX_STEPS)
                return model

            m2_primary = make_m2(False)
            w2_primary = make_w2(False)
            m2_common = make_m2(True)
            w1_common = make_w1(True)
            w2_common = make_w2(True)
            w2_corrupt = make_w2(True, corrupt_witness=True)
            w2_zero = make_w2(True, zero=True)

            for key, model in (
                ("m2_primary", m2_primary),
                ("w2_primary", w2_primary),
                ("m2_common", m2_common),
                ("w1_common", w1_common),
                ("w2_common", w2_common),
                ("w2_corrupt_witness", w2_corrupt),
                ("w2_zero", w2_zero),
            ):
                counts[key] += int(model.state_string() == target)

            final = w2_common.state_string()
            residual = _hamming(final, target)
            repaired_source = final[index] == target[index]
            exact = residual == 0
            target_cell_repaired += int(repaired_source)
            residual_hamming_total += residual
            if not exact:
                failed_trials += 1
                failed_residual_hamming_total += residual
                collateral_failure_trials += int(repaired_source)

            latch_trials += int(w2_common.latch_events > 0)
            latch_clear_trials += int(w2_common.latch_clear_events > 0)
            trials += 1

    rate = lambda key: counts[key] / trials
    return {
        "width": width,
        "height": height,
        "seed": spec["seed"],
        "trials": trials,
        "m2_primary": rate("m2_primary"),
        "w2_primary": rate("w2_primary"),
        "primary_gain_vs_m2": rate("w2_primary") - rate("m2_primary"),
        "m2_common": rate("m2_common"),
        "w1_common": rate("w1_common"),
        "w2_common": rate("w2_common"),
        "common_gain_vs_m2": rate("w2_common") - rate("m2_common"),
        "gain_vs_w1": rate("w2_common") - rate("w1_common"),
        "w2_corrupt_witness": rate("w2_corrupt_witness"),
        "causal_drop_when_witness_corrupted": rate("w2_common") - rate("w2_corrupt_witness"),
        "w2_zero": rate("w2_zero"),
        "zero_delta_vs_m2": rate("w2_zero") - rate("m2_common"),
        "latch_fraction": latch_trials / trials,
        "latch_clear_fraction": latch_clear_trials / trials,
        "target_cell_repaired_fraction": target_cell_repaired / trials,
        "collateral_failure_fraction": collateral_failure_trials / trials,
        "collateral_share_of_failures": (
            collateral_failure_trials / failed_trials if failed_trials else 0.0
        ),
        "mean_residual_hamming": residual_hamming_total / trials,
        "mean_failed_residual_hamming": (
            failed_residual_hamming_total / failed_trials if failed_trials else 0.0
        ),
    }


def main() -> None:
    rows = [_corpus(spec) for spec in CORPORA]
    summary = {
        "minimum_common_gain_vs_m2": min(r["common_gain_vs_m2"] for r in rows),
        "minimum_gain_vs_w1": min(r["gain_vs_w1"] for r in rows),
        "minimum_primary_gain_vs_m2": min(r["primary_gain_vs_m2"] for r in rows),
        "minimum_causal_drop_when_witness_corrupted": min(
            r["causal_drop_when_witness_corrupted"] for r in rows
        ),
        "minimum_latch_fraction": min(r["latch_fraction"] for r in rows),
        "minimum_target_cell_repaired_fraction": min(
            r["target_cell_repaired_fraction"] for r in rows
        ),
        "minimum_collateral_share_of_failures": min(
            r["collateral_share_of_failures"] for r in rows
        ),
        "zero_drive_exact_m2": all(abs(r["zero_delta_vs_m2"]) <= 1e-12 for r in rows),
    }
    passes = (
        summary["minimum_common_gain_vs_m2"] >= MIN_COMMON_GAIN_VS_M2
        and summary["minimum_gain_vs_w1"] >= MIN_GAIN_VS_W1
        and summary["minimum_primary_gain_vs_m2"] >= MIN_PRIMARY_GAIN_VS_M2
        and summary["minimum_causal_drop_when_witness_corrupted"]
        >= MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED
        and summary["zero_drive_exact_m2"]
    )
    print(json.dumps({
        "development_only": True,
        "mechanism_change": "latch localized binary intent across mixed phase",
        "frozen_witness_drive": WITNESS_DRIVE,
        "criteria": {
            "minimum_common_gain_vs_m2": MIN_COMMON_GAIN_VS_M2,
            "minimum_gain_vs_w1": MIN_GAIN_VS_W1,
            "minimum_primary_gain_vs_m2": MIN_PRIMARY_GAIN_VS_M2,
            "minimum_causal_drop_when_witness_corrupted": MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED,
            "zero_drive_must_match_m2": True,
        },
        "diagnostic_metrics_not_selection_gates": [
            "target_cell_repaired_fraction",
            "collateral_failure_fraction",
            "collateral_share_of_failures",
            "mean_residual_hamming",
            "mean_failed_residual_hamming",
        ],
        "rows": rows,
        "summary": summary,
        "passes": passes,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
