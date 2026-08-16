"""Frozen independent confirmation for MORPHOS-W4 selective authority.

This runner consumes the predeclared manifest and does not tune W4. The main
confirmation gate remains single-bit common-mode recovery because the W4
row/column parity witness is a single-error localization code. Two-bit
common-mode recovery is recorded separately as a diagnostic boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
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
from morphos.witness_selective import SelectiveAuthorityGrid2D

MANIFEST_PATH = Path(__file__).with_name("w4_confirmation_manifest.json")


def _load_protocol() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _run(
    cls,
    target: str,
    indices: list[int],
    config,
    hierarchy,
    m2_law,
    horizon: int,
    *,
    witness_drive: float,
    witness_commit_delay: int,
    common: bool = True,
    corrupt_witness: bool = False,
    zero_drive: bool = False,
):
    if cls is MultiReflectiveGrid2D:
        model = cls(target, config=config, law=hierarchy, reflective_law=m2_law)
    else:
        model = cls(
            target,
            config=config,
            law=hierarchy,
            reflective_law=m2_law,
            witness_law=WitnessLaw(
                witness_drive=0.0 if zero_drive else witness_drive,
                commit_delay=witness_commit_delay,
            ),
        )

    if common:
        for index in indices:
            _corrupt_all(model, index)
    else:
        model.perturb_primary(indices)
    if corrupt_witness:
        for index in indices:
            model.perturb_witness_for_cell(index)
    model.run([0.0] * horizon)
    return model


def _pair_indices(seed: int, target_index: int, cells: int, trials: int) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    counter = 0
    while len(pairs) < trials:
        digest = hashlib.sha256(
            f"w4-confirm-two-bit:{seed}:{target_index}:{counter}".encode("utf-8")
        ).digest()
        first = int.from_bytes(digest[:8], "big") % cells
        second = int.from_bytes(digest[8:16], "big") % cells
        counter += 1
        if first == second:
            continue
        pair = tuple(sorted((first, second)))
        if pair not in pairs:
            pairs.append(pair)
    return pairs


def _adaptation(config, hierarchy, m2_law, cells: int, protocol: dict) -> bool:
    model = SelectiveAuthorityGrid2D(
        "A" * cells,
        config=config,
        law=hierarchy,
        reflective_law=m2_law,
        witness_law=WitnessLaw(
            witness_drive=protocol["witness_drive"],
            commit_delay=protocol["witness_commit_delay"],
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


def _corpus(spec: dict, protocol: dict) -> dict:
    base_manifest = _manifest()
    width = spec["width"]
    height = spec["height"]
    cells = width * height
    config, hierarchy = _s2_components(base_manifest, width, height)
    m2_law = _m2_law(base_manifest)
    seeds = _sha_binary_seeds(spec["seed"], spec["samples"], cells)
    targets = _fixed_binary_targets(
        seeds,
        config,
        hierarchy,
        protocol["target_discovery_steps"],
    )[: protocol["max_targets"]]
    if not targets:
        raise RuntimeError("confirmation corpus produced no binary fixed targets")

    eval_horizon = protocol["evaluation_horizon"]
    retention_horizon = protocol["retention_horizon"]
    trials_per_target = protocol["trials_per_target"]
    witness_drive = protocol["witness_drive"]
    witness_commit_delay = protocol["witness_commit_delay"]

    counts = {
        "m2_common_8": 0,
        "w3_common_8": 0,
        "w4_common_8": 0,
        "w4_common_12": 0,
        "w4_corrupt_witness_8": 0,
        "w4_zero_8": 0,
        "m2_primary_8": 0,
        "w4_primary_8": 0,
        "w4_release_8": 0,
        "w4_release_12": 0,
        "w4_two_bit_8": 0,
        "w4_two_bit_unique_localization": 0,
    }
    single_trials = 0
    two_bit_trials = 0

    for target_index, target in enumerate(targets):
        indices = _noise_indices(
            spec["seed"], target_index, cells, trials_per_target
        )
        for index in indices:
            one = [index]
            m2 = _run(
                MultiReflectiveGrid2D,
                target,
                one,
                config,
                hierarchy,
                m2_law,
                eval_horizon,
                witness_drive=witness_drive,
                witness_commit_delay=witness_commit_delay,
            )
            w3 = _run(
                RecoveryFenceGrid2D,
                target,
                one,
                config,
                hierarchy,
                m2_law,
                eval_horizon,
                witness_drive=witness_drive,
                witness_commit_delay=witness_commit_delay,
            )
            w4_8 = _run(
                SelectiveAuthorityGrid2D,
                target,
                one,
                config,
                hierarchy,
                m2_law,
                eval_horizon,
                witness_drive=witness_drive,
                witness_commit_delay=witness_commit_delay,
            )
            w4_12 = _run(
                SelectiveAuthorityGrid2D,
                target,
                one,
                config,
                hierarchy,
                m2_law,
                retention_horizon,
                witness_drive=witness_drive,
                witness_commit_delay=witness_commit_delay,
            )
            corrupt = _run(
                SelectiveAuthorityGrid2D,
                target,
                one,
                config,
                hierarchy,
                m2_law,
                eval_horizon,
                witness_drive=witness_drive,
                witness_commit_delay=witness_commit_delay,
                corrupt_witness=True,
            )
            zero = _run(
                SelectiveAuthorityGrid2D,
                target,
                one,
                config,
                hierarchy,
                m2_law,
                eval_horizon,
                witness_drive=witness_drive,
                witness_commit_delay=witness_commit_delay,
                zero_drive=True,
            )
            m2_primary = _run(
                MultiReflectiveGrid2D,
                target,
                one,
                config,
                hierarchy,
                m2_law,
                eval_horizon,
                witness_drive=witness_drive,
                witness_commit_delay=witness_commit_delay,
                common=False,
            )
            w4_primary = _run(
                SelectiveAuthorityGrid2D,
                target,
                one,
                config,
                hierarchy,
                m2_law,
                eval_horizon,
                witness_drive=witness_drive,
                witness_commit_delay=witness_commit_delay,
                common=False,
            )

            for key, model in (
                ("m2_common_8", m2),
                ("w3_common_8", w3),
                ("w4_common_8", w4_8),
                ("w4_common_12", w4_12),
                ("w4_corrupt_witness_8", corrupt),
                ("w4_zero_8", zero),
                ("m2_primary_8", m2_primary),
                ("w4_primary_8", w4_primary),
            ):
                counts[key] += int(model.state_string() == target)
            counts["w4_release_8"] += int(w4_8.fence_release_events > 0)
            counts["w4_release_12"] += int(w4_12.fence_release_events > 0)
            single_trials += 1

        for first, second in _pair_indices(
            spec["seed"], target_index, cells, trials_per_target
        ):
            two = SelectiveAuthorityGrid2D(
                target,
                config=config,
                law=hierarchy,
                reflective_law=m2_law,
                witness_law=WitnessLaw(
                    witness_drive=witness_drive,
                    commit_delay=witness_commit_delay,
                ),
            )
            _corrupt_all(two, first)
            _corrupt_all(two, second)
            counts["w4_two_bit_unique_localization"] += int(
                two.localized_error_index() is not None
            )
            two.run([0.0] * eval_horizon)
            counts["w4_two_bit_8"] += int(two.state_string() == target)
            two_bit_trials += 1

    rate = lambda key: counts[key] / single_trials
    common8 = rate("w4_common_8")
    common12 = rate("w4_common_12")
    return {
        "width": width,
        "height": height,
        "seed": spec["seed"],
        "single_bit_trials": single_trials,
        "m2_common_8": rate("m2_common_8"),
        "w3_common_8": rate("w3_common_8"),
        "w4_common_8": common8,
        "w4_common_12": common12,
        "gain_vs_w3_at_8": common8 - rate("w3_common_8"),
        "primary_gain_vs_m2": rate("w4_primary_8") - rate("m2_primary_8"),
        "retention_delta_12_minus_8": common12 - common8,
        "w4_corrupt_witness_8": rate("w4_corrupt_witness_8"),
        "causal_drop_when_witness_corrupted": common8 - rate("w4_corrupt_witness_8"),
        "zero_drive_delta_vs_m2": rate("w4_zero_8") - rate("m2_common_8"),
        "fence_release_fraction_8": rate("w4_release_8"),
        "fence_release_fraction_12": rate("w4_release_12"),
        "two_bit_diagnostic": {
            "trials": two_bit_trials,
            "exact_recovery_at_8": counts["w4_two_bit_8"] / two_bit_trials,
            "unique_single_cell_localization_fraction": (
                counts["w4_two_bit_unique_localization"] / two_bit_trials
            ),
        },
    }


def run_confirmation() -> dict:
    protocol = _load_protocol()
    rows = [_corpus(spec, protocol) for spec in protocol["confirmation_corpora"]]
    gate = protocol["predeclared_gates"]

    sizes = sorted({(row["width"], row["height"]) for row in rows})
    base_manifest = _manifest()
    adaptation = {}
    for width, height in sizes:
        config, hierarchy = _s2_components(base_manifest, width, height)
        adaptation[f"{width}x{height}"] = _adaptation(
            config, hierarchy, _m2_law(base_manifest), width * height, protocol
        )

    summary = {
        "minimum_common_recovery_at_8": min(r["w4_common_8"] for r in rows),
        "minimum_common_recovery_at_12": min(r["w4_common_12"] for r in rows),
        "minimum_gain_vs_w3_at_8": min(r["gain_vs_w3_at_8"] for r in rows),
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
        "adaptation_by_size": adaptation,
        "two_bit_mean_exact_recovery_at_8": sum(
            r["two_bit_diagnostic"]["exact_recovery_at_8"] for r in rows
        ) / len(rows),
        "two_bit_mean_unique_single_cell_localization_fraction": sum(
            r["two_bit_diagnostic"]["unique_single_cell_localization_fraction"]
            for r in rows
        ) / len(rows),
    }

    passes = (
        summary["minimum_common_recovery_at_8"]
        >= gate["minimum_common_recovery_at_8_every_corpus"]
        and summary["minimum_common_recovery_at_12"]
        >= gate["minimum_common_recovery_at_12_every_corpus"]
        and summary["minimum_gain_vs_w3_at_8"]
        >= gate["minimum_gain_vs_w3_at_8_every_corpus"]
        and summary["minimum_primary_gain_vs_m2"]
        >= gate["minimum_primary_gain_vs_m2_every_corpus"]
        and summary["minimum_retention_delta_12_minus_8"]
        >= -gate["maximum_retention_drop_8_to_12_every_corpus"]
        and summary["minimum_causal_drop_when_witness_corrupted"]
        >= gate["minimum_causal_drop_when_witness_corrupted_every_corpus"]
        and summary["zero_drive_exact_m2"]
        and all(adaptation.values())
    )

    return {
        "schema": "cosmic-organics/w4-confirmation-full-0.1",
        "frozen_from_head": protocol["frozen_from_head"],
        "confirmation_only_no_retuning": True,
        "criteria": gate,
        "rows": rows,
        "summary": summary,
        "passes": passes,
        "diagnostic_note": (
            "two-bit common-mode results are diagnostic only and are not part "
            "of the single-bit W4 confirmation gate"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_confirmation()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
