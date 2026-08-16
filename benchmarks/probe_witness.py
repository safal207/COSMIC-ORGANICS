"""Non-evidence development probe for MORPHOS-W1 independent witnesses.

The probe asks whether a compact row/column parity witness can recover a
single-bit common-mode fault that corrupts primary plus all copy-like mirrors.
Development seeds here must not be reused for frozen confirmation.
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

CORPORA = [
    {"width": 5, "height": 5, "seed": 202608155001, "samples": 96},
    {"width": 7, "height": 7, "seed": 202608155011, "samples": 96},
    {"width": 9, "height": 9, "seed": 202608155021, "samples": 72},
]
CANDIDATES = [0.25, 0.5, 0.75, 1.0]
RELAX_STEPS = 6
MAX_TARGETS = 12
TRIALS_PER_TARGET = 8
WITNESS_COMMIT_DELAY = 8

# Predeclared before observing this development probe.
MIN_COMMON_MODE_GAIN_VS_M2 = 0.25
MIN_PRIMARY_GAIN_VS_M2 = 0.0
MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED = 0.10


def _load_manifest():
    return json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))


def _perturb_all_copy_planes(model, index: int) -> None:
    model.perturb_primary([index])
    model.perturb_local_mirror([index])
    model.perturb_domain_mirror([index])
    model.perturb_system_mirror([index])


def _corpus(drive: float, spec: dict) -> dict:
    manifest = _load_manifest()
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
        "w1_primary": 0,
        "m2_common": 0,
        "w1_common": 0,
        "w1_witness_corrupted": 0,
        "w1_zero_drive": 0,
    }
    localized = 0
    trials = 0

    for target_index, target in enumerate(targets):
        indices = _noise_indices(
            spec["seed"], target_index, width * height, TRIALS_PER_TARGET
        )
        for index in indices:
            def m2_case(*, common: bool) -> MultiReflectiveGrid2D:
                model = MultiReflectiveGrid2D(
                    target,
                    config=config,
                    law=hierarchy,
                    reflective_law=m2_law,
                )
                if common:
                    _perturb_all_copy_planes(model, index)
                else:
                    model.perturb_primary([index])
                model.run([0.0] * RELAX_STEPS)
                return model

            def w1_case(*, common: bool, corrupt_witness: bool = False, zero: bool = False):
                model = IndependentWitnessGrid2D(
                    target,
                    config=config,
                    law=hierarchy,
                    reflective_law=m2_law,
                    witness_law=WitnessLaw(
                        witness_drive=0.0 if zero else drive,
                        commit_delay=WITNESS_COMMIT_DELAY,
                    ),
                )
                if common:
                    _perturb_all_copy_planes(model, index)
                else:
                    model.perturb_primary([index])
                if corrupt_witness:
                    model.perturb_witness_for_cell(index)
                if model.localized_error_index() == index:
                    nonlocal_localized[0] += 1
                model.run([0.0] * RELAX_STEPS)
                return model

            nonlocal_localized = [0]
            m2_primary = m2_case(common=False)
            w1_primary = w1_case(common=False)
            m2_common = m2_case(common=True)
            w1_common = w1_case(common=True)
            w1_corrupt = w1_case(common=True, corrupt_witness=True)
            w1_zero = w1_case(common=True, zero=True)
            localized += nonlocal_localized[0]

            for key, model in (
                ("m2_primary", m2_primary),
                ("w1_primary", w1_primary),
                ("m2_common", m2_common),
                ("w1_common", w1_common),
                ("w1_witness_corrupted", w1_corrupt),
                ("w1_zero_drive", w1_zero),
            ):
                counts[key] += int(model.state_string() == target)
            trials += 1

    rate = lambda key: counts[key] / trials
    primary_gain = rate("w1_primary") - rate("m2_primary")
    common_gain = rate("w1_common") - rate("m2_common")
    causal_drop = rate("w1_common") - rate("w1_witness_corrupted")
    return {
        "width": width,
        "height": height,
        "seed": spec["seed"],
        "trials": trials,
        "m2_primary": rate("m2_primary"),
        "w1_primary": rate("w1_primary"),
        "primary_gain_vs_m2": primary_gain,
        "m2_common_mode": rate("m2_common"),
        "w1_common_mode": rate("w1_common"),
        "common_mode_gain_vs_m2": common_gain,
        "w1_witness_corrupted": rate("w1_witness_corrupted"),
        "causal_drop_when_witness_corrupted": causal_drop,
        "w1_zero_drive": rate("w1_zero_drive"),
        "zero_drive_delta_vs_m2_common": rate("w1_zero_drive") - rate("m2_common"),
        "initial_localization_fraction": localized / (4 * trials),
    }


def main() -> None:
    candidates = []
    selected = None
    for drive in CANDIDATES:
        rows = [_corpus(drive, spec) for spec in CORPORA]
        min_common = min(row["common_mode_gain_vs_m2"] for row in rows)
        min_primary = min(row["primary_gain_vs_m2"] for row in rows)
        min_causal_drop = min(
            row["causal_drop_when_witness_corrupted"] for row in rows
        )
        zero_drive_exact = all(
            abs(row["zero_drive_delta_vs_m2_common"]) <= 1e-12 for row in rows
        )
        passes = (
            min_common >= MIN_COMMON_MODE_GAIN_VS_M2
            and min_primary >= MIN_PRIMARY_GAIN_VS_M2
            and min_causal_drop >= MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED
            and zero_drive_exact
        )
        item = {
            "witness_drive": drive,
            "min_common_mode_gain_vs_m2": min_common,
            "min_primary_gain_vs_m2": min_primary,
            "min_causal_drop_when_witness_corrupted": min_causal_drop,
            "zero_drive_exact_m2": zero_drive_exact,
            "passes": passes,
            "rows": rows,
        }
        candidates.append(item)
        if selected is None and passes:
            selected = drive

    print(json.dumps({
        "development_only": True,
        "selection_rule": "minimum passing witness_drive",
        "criteria": {
            "minimum_common_mode_gain_vs_m2": MIN_COMMON_MODE_GAIN_VS_M2,
            "minimum_primary_gain_vs_m2": MIN_PRIMARY_GAIN_VS_M2,
            "minimum_causal_drop_when_witness_corrupted": MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED,
            "zero_drive_must_match_m2": True,
        },
        "candidates": candidates,
        "selected": selected,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
