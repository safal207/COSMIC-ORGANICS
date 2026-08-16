"""Development probe for MORPHOS-W4 selective authority fencing.

W4 freezes every W3/W2 amplitude and timing choice. It changes only authority
resolution at the localized repair cell: mirror values that disagree with the
independently witnessed endpoint are ignored there; agreeing mirror values and
all mirror evidence elsewhere remain active.
"""
from __future__ import annotations

import json

from benchmarks.probe_witness_persistent import (
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
from morphos.witness import WitnessLaw
from morphos.witness_fence import RecoveryFenceGrid2D
from morphos.witness_persistent import PersistentWitnessGrid2D
from morphos.witness_selective import SelectiveAuthorityGrid2D

CORPORA = [
    {"width": 5, "height": 5, "seed": 202608159001, "samples": 96},
    {"width": 7, "height": 7, "seed": 202608159011, "samples": 96},
    {"width": 9, "height": 9, "seed": 202608159021, "samples": 72},
]
TARGET_DISCOVERY_STEPS = 6
EVALUATION_HORIZON = 8
RETENTION_HORIZON = 12

# Predeclared before observing W4 development data.
MIN_COMMON_RECOVERY = 0.80
MIN_GAIN_VS_W3 = 0.05
MIN_PRIMARY_GAIN_VS_M2 = 0.0
MAX_RETENTION_DROP_8_TO_12 = 0.02
MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED = 0.20


def _run(cls, target, index, config, hierarchy, m2_law, horizon, *,
         common=True, corrupt_witness=False, zero_drive=False):
    if cls is MultiReflectiveGrid2D:
        model = cls(target, config=config, law=hierarchy, reflective_law=m2_law)
    else:
        model = cls(
            target,
            config=config,
            law=hierarchy,
            reflective_law=m2_law,
            witness_law=WitnessLaw(
                witness_drive=0.0 if zero_drive else WITNESS_DRIVE,
                commit_delay=WITNESS_COMMIT_DELAY,
            ),
        )
    if common:
        _corrupt_all(model, index)
    else:
        model.perturb_primary([index])
    if corrupt_witness:
        model.perturb_witness_for_cell(index)
    model.run([0.0] * horizon)
    return model


def _adaptation(config, hierarchy, m2_law, cells: int) -> bool:
    model = SelectiveAuthorityGrid2D(
        "A" * cells,
        config=config,
        law=hierarchy,
        reflective_law=m2_law,
        witness_law=WitnessLaw(
            witness_drive=WITNESS_DRIVE,
            commit_delay=WITNESS_COMMIT_DELAY,
        ),
    )
    initial_witness = model.witness_signature()
    model.run([2.0] * 18)
    model.run([0.0] * 16)
    expected = "C" * cells
    return (
        model.state_string() == expected
        and model.local_mirror_string() == expected
        and model.domain_mirror_string() == expected
        and model.system_mirror_string() == expected
        and model.witness_signature() != initial_witness
    )


def _corpus(spec: dict) -> dict:
    manifest = _manifest()
    width = spec["width"]
    height = spec["height"]
    cells = width * height
    config, hierarchy = _s2_components(manifest, width, height)
    m2_law = _m2_law(manifest)
    seeds = _sha_binary_seeds(spec["seed"], spec["samples"], cells)
    targets = _fixed_binary_targets(
        seeds, config, hierarchy, TARGET_DISCOVERY_STEPS
    )[:MAX_TARGETS]
    if not targets:
        raise RuntimeError("W4 development corpus produced no binary fixed targets")

    counts = {
        "m2_common_8": 0,
        "w2_common_8": 0,
        "w3_common_8": 0,
        "w4_common_8": 0,
        "w4_common_12": 0,
        "w4_corrupt_8": 0,
        "w4_zero_8": 0,
        "m2_primary_8": 0,
        "w4_primary_8": 0,
        "w4_release_8": 0,
        "w4_release_12": 0,
    }
    suppressed_total = 0
    preserved_total = 0
    trials = 0

    for target_index, target in enumerate(targets):
        indices = _noise_indices(
            spec["seed"], target_index, cells, TRIALS_PER_TARGET
        )
        for index in indices:
            m2 = _run(
                MultiReflectiveGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON,
            )
            w2 = _run(
                PersistentWitnessGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON,
            )
            w3 = _run(
                RecoveryFenceGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON,
            )
            w4_8 = _run(
                SelectiveAuthorityGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON,
            )
            w4_12 = _run(
                SelectiveAuthorityGrid2D, target, index, config, hierarchy, m2_law,
                RETENTION_HORIZON,
            )
            w4_corrupt = _run(
                SelectiveAuthorityGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON, corrupt_witness=True,
            )
            w4_zero = _run(
                SelectiveAuthorityGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON, zero_drive=True,
            )
            m2_primary = _run(
                MultiReflectiveGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON, common=False,
            )
            w4_primary = _run(
                SelectiveAuthorityGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON, common=False,
            )

            for key, model in (
                ("m2_common_8", m2),
                ("w2_common_8", w2),
                ("w3_common_8", w3),
                ("w4_common_8", w4_8),
                ("w4_common_12", w4_12),
                ("w4_corrupt_8", w4_corrupt),
                ("w4_zero_8", w4_zero),
                ("m2_primary_8", m2_primary),
                ("w4_primary_8", w4_primary),
            ):
                counts[key] += int(model.state_string() == target)
            counts["w4_release_8"] += int(w4_8.fence_release_events > 0)
            counts["w4_release_12"] += int(w4_12.fence_release_events > 0)
            suppressed_total += w4_8.suppressed_mirror_contributions
            preserved_total += w4_8.preserved_mirror_contributions
            trials += 1

    rate = lambda key: counts[key] / trials
    w4_8 = rate("w4_common_8")
    w4_12 = rate("w4_common_12")
    return {
        "width": width,
        "height": height,
        "seed": spec["seed"],
        "trials": trials,
        "m2_common_8": rate("m2_common_8"),
        "w2_common_8": rate("w2_common_8"),
        "w3_common_8": rate("w3_common_8"),
        "w4_common_8": w4_8,
        "w4_common_12": w4_12,
        "gain_vs_w3_at_8": w4_8 - rate("w3_common_8"),
        "gain_vs_w2_at_8": w4_8 - rate("w2_common_8"),
        "retention_delta_12_minus_8": w4_12 - w4_8,
        "w4_corrupt_witness_8": rate("w4_corrupt_8"),
        "causal_drop_when_witness_corrupted": w4_8 - rate("w4_corrupt_8"),
        "zero_drive_delta_vs_m2": rate("w4_zero_8") - rate("m2_common_8"),
        "primary_gain_vs_m2": rate("w4_primary_8") - rate("m2_primary_8"),
        "fence_release_fraction_8": rate("w4_release_8"),
        "fence_release_fraction_12": rate("w4_release_12"),
        "mean_suppressed_mirror_contributions": suppressed_total / trials,
        "mean_preserved_target_mirror_contributions": preserved_total / trials,
        "adaptation_pass": _adaptation(config, hierarchy, m2_law, cells),
    }


def main() -> None:
    rows = [_corpus(spec) for spec in CORPORA]
    summary = {
        "minimum_common_recovery_at_8": min(r["w4_common_8"] for r in rows),
        "minimum_common_recovery_at_12": min(r["w4_common_12"] for r in rows),
        "minimum_gain_vs_w3_at_8": min(r["gain_vs_w3_at_8"] for r in rows),
        "minimum_gain_vs_w2_at_8": min(r["gain_vs_w2_at_8"] for r in rows),
        "minimum_primary_gain_vs_m2": min(r["primary_gain_vs_m2"] for r in rows),
        "minimum_retention_delta_12_minus_8": min(
            r["retention_delta_12_minus_8"] for r in rows
        ),
        "minimum_causal_drop_when_witness_corrupted": min(
            r["causal_drop_when_witness_corrupted"] for r in rows
        ),
        "zero_drive_exact_m2": all(
            abs(r["zero_drive_delta_vs_m2"]) <= 1e-12 for r in rows
        ),
        "adaptation_all_sizes": all(r["adaptation_pass"] for r in rows),
    }
    passes = (
        summary["minimum_common_recovery_at_8"] >= MIN_COMMON_RECOVERY
        and summary["minimum_common_recovery_at_12"] >= MIN_COMMON_RECOVERY
        and summary["minimum_gain_vs_w3_at_8"] >= MIN_GAIN_VS_W3
        and summary["minimum_primary_gain_vs_m2"] >= MIN_PRIMARY_GAIN_VS_M2
        and summary["minimum_retention_delta_12_minus_8"]
        >= -MAX_RETENTION_DROP_8_TO_12
        and summary["minimum_causal_drop_when_witness_corrupted"]
        >= MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED
        and summary["zero_drive_exact_m2"]
        and summary["adaptation_all_sizes"]
    )
    print(json.dumps({
        "development_only": True,
        "mechanism": "selectively suppress only target-cell mirror claims that contradict the witnessed endpoint",
        "new_tuned_amplitude": False,
        "frozen_witness_drive": WITNESS_DRIVE,
        "evaluation_horizon": EVALUATION_HORIZON,
        "retention_horizon": RETENTION_HORIZON,
        "criteria": {
            "minimum_common_recovery": MIN_COMMON_RECOVERY,
            "minimum_gain_vs_w3_at_8": MIN_GAIN_VS_W3,
            "minimum_primary_gain_vs_m2": MIN_PRIMARY_GAIN_VS_M2,
            "maximum_retention_drop_8_to_12": MAX_RETENTION_DROP_8_TO_12,
            "minimum_causal_drop_when_witness_corrupted": MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED,
            "zero_drive_exact_m2": True,
            "adaptation_all_sizes": True,
        },
        "rows": rows,
        "summary": summary,
        "passes": passes,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
