"""Development probe for MORPHOS-W3 witness-validated recovery fence.

W3 introduces no new coupling amplitude. It freezes W2 witness_drive=0.25 and
tests a two-phase authority rule: while a quiescent parity-detected repair is
open, stale copy-like mirrors are quarantined; their authority returns only
after primary, witness, and all mirror planes recommit to one state.
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

CORPORA = [
    {"width": 5, "height": 5, "seed": 202608158001, "samples": 96},
    {"width": 7, "height": 7, "seed": 202608158011, "samples": 96},
    {"width": 9, "height": 9, "seed": 202608158021, "samples": 72},
]
TARGET_DISCOVERY_STEPS = 6
# Derived before observation: 2 ticks for A<->M<->C + 5 stable ticks for
# system-mirror recommit + 1 stabilization tick.
EVALUATION_HORIZON = 8
RETENTION_HORIZON = 12

# Predeclared development gates.
MIN_COMMON_RECOVERY = 0.80
MIN_GAIN_VS_W2_AT_8 = 0.20
MAX_RETENTION_DROP_8_TO_12 = 0.02
MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED = 0.20
MIN_PRIMARY_GAIN_VS_M2 = 0.0


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
    model = RecoveryFenceGrid2D(
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
        and model.witness_commit_events > 0
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
        raise RuntimeError("W3 development corpus produced no binary fixed targets")

    counts = {
        "m2_8": 0,
        "w2_8": 0,
        "w3_8": 0,
        "w3_12": 0,
        "w3_corrupt_8": 0,
        "w3_zero_8": 0,
        "m2_primary_8": 0,
        "w3_primary_8": 0,
        "w3_released_8": 0,
        "w3_released_12": 0,
    }
    trials = 0

    for target_index, target in enumerate(targets):
        indices = _noise_indices(
            spec["seed"], target_index, cells, TRIALS_PER_TARGET
        )
        for index in indices:
            m2_8 = _run(
                MultiReflectiveGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON,
            )
            w2_8 = _run(
                PersistentWitnessGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON,
            )
            w3_8 = _run(
                RecoveryFenceGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON,
            )
            w3_12 = _run(
                RecoveryFenceGrid2D, target, index, config, hierarchy, m2_law,
                RETENTION_HORIZON,
            )
            w3_corrupt = _run(
                RecoveryFenceGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON, corrupt_witness=True,
            )
            w3_zero = _run(
                RecoveryFenceGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON, zero_drive=True,
            )
            m2_primary = _run(
                MultiReflectiveGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON, common=False,
            )
            w3_primary = _run(
                RecoveryFenceGrid2D, target, index, config, hierarchy, m2_law,
                EVALUATION_HORIZON, common=False,
            )

            for key, model in (
                ("m2_8", m2_8),
                ("w2_8", w2_8),
                ("w3_8", w3_8),
                ("w3_12", w3_12),
                ("w3_corrupt_8", w3_corrupt),
                ("w3_zero_8", w3_zero),
                ("m2_primary_8", m2_primary),
                ("w3_primary_8", w3_primary),
            ):
                counts[key] += int(model.state_string() == target)
            counts["w3_released_8"] += int(w3_8.fence_release_events > 0)
            counts["w3_released_12"] += int(w3_12.fence_release_events > 0)
            trials += 1

    rate = lambda key: counts[key] / trials
    w3_8 = rate("w3_8")
    w3_12 = rate("w3_12")
    return {
        "width": width,
        "height": height,
        "seed": spec["seed"],
        "trials": trials,
        "m2_common_8": rate("m2_8"),
        "w2_common_8": rate("w2_8"),
        "w3_common_8": w3_8,
        "w3_common_12": w3_12,
        "gain_vs_w2_at_8": w3_8 - rate("w2_8"),
        "gain_vs_m2_at_8": w3_8 - rate("m2_8"),
        "retention_delta_12_minus_8": w3_12 - w3_8,
        "w3_corrupt_witness_8": rate("w3_corrupt_8"),
        "causal_drop_when_witness_corrupted": w3_8 - rate("w3_corrupt_8"),
        "zero_drive_delta_vs_m2": rate("w3_zero_8") - rate("m2_8"),
        "primary_gain_vs_m2": rate("w3_primary_8") - rate("m2_primary_8"),
        "fence_release_fraction_8": rate("w3_released_8"),
        "fence_release_fraction_12": rate("w3_released_12"),
        "adaptation_pass": _adaptation(config, hierarchy, m2_law, cells),
    }


def main() -> None:
    rows = [_corpus(spec) for spec in CORPORA]
    summary = {
        "minimum_common_recovery_at_8": min(r["w3_common_8"] for r in rows),
        "minimum_common_recovery_at_12": min(r["w3_common_12"] for r in rows),
        "minimum_gain_vs_w2_at_8": min(r["gain_vs_w2_at_8"] for r in rows),
        "minimum_retention_delta_12_minus_8": min(
            r["retention_delta_12_minus_8"] for r in rows
        ),
        "minimum_causal_drop_when_witness_corrupted": min(
            r["causal_drop_when_witness_corrupted"] for r in rows
        ),
        "minimum_primary_gain_vs_m2": min(r["primary_gain_vs_m2"] for r in rows),
        "zero_drive_exact_m2": all(
            abs(r["zero_drive_delta_vs_m2"]) <= 1e-12 for r in rows
        ),
        "adaptation_all_sizes": all(r["adaptation_pass"] for r in rows),
    }
    passes = (
        summary["minimum_common_recovery_at_8"] >= MIN_COMMON_RECOVERY
        and summary["minimum_common_recovery_at_12"] >= MIN_COMMON_RECOVERY
        and summary["minimum_gain_vs_w2_at_8"] >= MIN_GAIN_VS_W2_AT_8
        and summary["minimum_retention_delta_12_minus_8"]
        >= -MAX_RETENTION_DROP_8_TO_12
        and summary["minimum_causal_drop_when_witness_corrupted"]
        >= MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED
        and summary["minimum_primary_gain_vs_m2"] >= MIN_PRIMARY_GAIN_VS_M2
        and summary["zero_drive_exact_m2"]
        and summary["adaptation_all_sizes"]
    )
    print(json.dumps({
        "development_only": True,
        "mechanism": "witness-validated mirror quarantine and two-phase recommit",
        "new_tuned_amplitude": False,
        "frozen_witness_drive": WITNESS_DRIVE,
        "evaluation_horizon": EVALUATION_HORIZON,
        "retention_horizon": RETENTION_HORIZON,
        "criteria": {
            "minimum_common_recovery": MIN_COMMON_RECOVERY,
            "minimum_gain_vs_w2_at_8": MIN_GAIN_VS_W2_AT_8,
            "maximum_retention_drop_8_to_12": MAX_RETENTION_DROP_8_TO_12,
            "minimum_causal_drop_when_witness_corrupted": MIN_CAUSAL_DROP_WHEN_WITNESS_CORRUPTED,
            "minimum_primary_gain_vs_m2": MIN_PRIMARY_GAIN_VS_M2,
            "zero_drive_exact_m2": True,
            "adaptation_all_sizes": True,
        },
        "rows": rows,
        "summary": summary,
        "passes": passes,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
