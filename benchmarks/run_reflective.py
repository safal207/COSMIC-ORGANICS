"""Confirm MORPHOS-M1 reflective recovery on frozen S2 attractors."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalGrid2D, HierarchicalLaw
from morphos.reflective import ReflectiveGrid2D, ReflectiveLaw
from morphos.scale_aware import ScaleLaw

DEFAULT_MANIFEST = Path(__file__).with_name("reflective_manifest.json")


def _sha_binary_seeds(seed: int, samples: int, cells: int) -> list[str]:
    values: list[str] = []
    for sample in range(samples):
        chunks = b""
        counter = 0
        while len(chunks) * 8 < cells:
            chunks += hashlib.sha256(
                f"{seed}:{sample}:{counter}".encode("ascii")
            ).digest()
            counter += 1
        bits = "".join(f"{byte:08b}" for byte in chunks)[:cells]
        values.append("".join("C" if bit == "1" else "A" for bit in bits))
    return values


def _flip_binary(state: str, index: int) -> str:
    values = list(state)
    if values[index] == "A":
        values[index] = "C"
    elif values[index] == "C":
        values[index] = "A"
    else:
        raise ValueError("binary perturbation requires A/C target")
    return "".join(values)


def _base_config(spec: dict[str, Any]) -> Grid2DConfig:
    return Grid2DConfig(width=5, height=5, **spec)


def _s2_components(
    manifest: dict[str, Any],
    width: int,
    height: int,
) -> tuple[Grid2DConfig, HierarchicalLaw]:
    s2 = manifest["frozen_s2"]
    base = _base_config(s2["base_candidate"])
    scaled = ScaleLaw(
        reference_linear_size=s2["reference_linear_size"],
        exponent=s2["scale_exponent"],
    ).apply(base, width=width, height=height)
    hierarchy = HierarchicalLaw(
        reference_linear_size=s2["reference_linear_size"],
        exponent=s2["hierarchy_exponent"],
        domain_size=s2["domain_size"],
    )
    return scaled, hierarchy


def _s2_relax(
    initial: str,
    config: Grid2DConfig,
    hierarchy: HierarchicalLaw,
    steps: int,
) -> tuple[str, int]:
    model = HierarchicalGrid2D(initial, config=config, law=hierarchy)
    model.run([0.0] * steps)
    return model.state_string(), model.transitions


def _fixed_binary_targets(
    seeds: list[str],
    config: Grid2DConfig,
    hierarchy: HierarchicalLaw,
    steps: int,
) -> list[str]:
    finals: dict[str, int] = {}
    for seed in seeds:
        final, _ = _s2_relax(seed, config, hierarchy, steps)
        finals[final] = finals.get(final, 0) + 1

    targets: list[str] = []
    for state in finals:
        next_state, _ = _s2_relax(state, config, hierarchy, steps)
        if next_state == state and "M" not in state:
            targets.append(state)
    return targets


def _noise_indices(
    seed: int,
    target_index: int,
    cells: int,
    count: int,
) -> list[int]:
    return sorted(
        range(cells),
        key=lambda index: hashlib.sha256(
            f"{seed}:noise:{target_index}:{index}".encode("ascii")
        ).digest(),
    )[:count]


def _corpus_metrics(
    manifest: dict[str, Any],
    size: dict[str, Any],
) -> dict[str, Any]:
    width = size["width"]
    height = size["height"]
    seed = size["seed"]
    steps = manifest["relax_steps"]
    config, hierarchy = _s2_components(manifest, width, height)
    confirmation = manifest["confirmation"]
    reflective = manifest["reflective"]
    law = ReflectiveLaw(
        mirror_coupling=reflective["mirror_coupling"],
        commit_delay=reflective["commit_delay"],
    )

    seeds = _sha_binary_seeds(seed, size["samples"], width * height)
    targets = _fixed_binary_targets(seeds, config, hierarchy, steps)[
        : confirmation["max_targets"]
    ]

    recovered_s2 = 0
    recovered_m1 = 0
    recovered_co = 0
    s2_cost = 0
    m1_cost = 0
    trials = 0

    for target_index, target in enumerate(targets):
        indices = _noise_indices(
            seed,
            target_index,
            width * height,
            confirmation["trials_per_target"],
        )
        for index in indices:
            corrupted = _flip_binary(target, index)

            baseline = HierarchicalGrid2D(
                corrupted,
                config=config,
                law=hierarchy,
            )
            baseline.run([0.0] * steps)

            reflective_model = ReflectiveGrid2D(
                target,
                config=config,
                law=hierarchy,
                reflective_law=law,
            )
            reflective_model.perturb_primary([index])
            reflective_model.run([0.0] * steps)

            co_corrupted = ReflectiveGrid2D(
                target,
                config=config,
                law=hierarchy,
                reflective_law=law,
            )
            co_corrupted.perturb_primary([index])
            co_corrupted.perturb_mirror([index])
            co_corrupted.run([0.0] * steps)

            recovered_s2 += int(baseline.state_string() == target)
            recovered_m1 += int(reflective_model.state_string() == target)
            recovered_co += int(co_corrupted.state_string() == target)
            s2_cost += baseline.transitions
            m1_cost += reflective_model.transitions
            trials += 1

    if not trials:
        raise RuntimeError("confirmation corpus produced no binary fixed targets")

    s2_recovery = recovered_s2 / trials
    m1_recovery = recovered_m1 / trials
    co_recovery = recovered_co / trials
    return {
        "width": width,
        "height": height,
        "seed": seed,
        "samples": size["samples"],
        "binary_fixed_targets": len(targets),
        "trials": trials,
        "s2_recovery_1bit": s2_recovery,
        "m1_recovery_1bit": m1_recovery,
        "recovery_gain_vs_s2": m1_recovery - s2_recovery,
        "co_corruption_recovery_1bit": co_recovery,
        "co_corruption_gain_vs_s2": co_recovery - s2_recovery,
        "s2_transition_cost": s2_cost / trials,
        "m1_transition_cost": m1_cost / trials,
        "transition_cost_ratio_vs_s2": (
            m1_cost / s2_cost if s2_cost else None
        ),
    }


def _adaptation_case(
    manifest: dict[str, Any],
    width: int,
    height: int,
    start: str,
    target: str,
    stimulus: float,
) -> dict[str, Any]:
    config, hierarchy = _s2_components(manifest, width, height)
    reflective = manifest["reflective"]
    adaptation = manifest["adaptation"]
    model = ReflectiveGrid2D(
        start * (width * height),
        config=config,
        law=hierarchy,
        reflective_law=ReflectiveLaw(
            mirror_coupling=reflective["mirror_coupling"],
            commit_delay=reflective["commit_delay"],
        ),
    )

    for _ in range(adaptation["drive_steps"]):
        model.step(stimulus)
    for _ in range(adaptation["settle_steps"]):
        model.step(0.0)

    cells = width * height
    return {
        "width": width,
        "height": height,
        "direction": f"{start}_to_{target}",
        "primary_after_settle_target_fraction": (
            model.state_string().count(target) / cells
        ),
        "mirror_after_settle_target_fraction": (
            model.mirror_string().count(target) / cells
        ),
        "transitions": model.transitions,
        "mirror_commits": model.mirror_commits,
    }


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    confirmation = [
        _corpus_metrics(manifest, size)
        for size in manifest["confirmation"]["corpora"]
    ]

    adaptation_rows: list[dict[str, Any]] = []
    amplitude = manifest["adaptation"]["stimulus_amplitude"]
    for size in manifest["adaptation"]["sizes"]:
        width = size["width"]
        height = size["height"]
        adaptation_rows.append(
            _adaptation_case(manifest, width, height, "A", "C", amplitude)
        )
        adaptation_rows.append(
            _adaptation_case(manifest, width, height, "C", "A", -amplitude)
        )

    gains = [row["recovery_gain_vs_s2"] for row in confirmation]
    co_gains = [
        abs(row["co_corruption_gain_vs_s2"]) for row in confirmation
    ]
    cost_ratios = [
        row["transition_cost_ratio_vs_s2"]
        for row in confirmation
        if row["transition_cost_ratio_vs_s2"] is not None
    ]
    gates = manifest["gates"]

    adaptation_pass = all(
        row["primary_after_settle_target_fraction"] == 1.0
        and row["mirror_after_settle_target_fraction"] == 1.0
        for row in adaptation_rows
    )
    recovery_pass = all(
        gain >= gates["minimum_recovery_gain"] for gain in gains
    )
    co_control_pass = all(
        gain <= gates["max_abs_co_corruption_gain"] for gain in co_gains
    )

    summary = {
        "confirmation_corpora": len(confirmation),
        "mirror_coupling": manifest["reflective"]["mirror_coupling"],
        "commit_delay": manifest["reflective"]["commit_delay"],
        "minimum_required_recovery_gain": gates["minimum_recovery_gain"],
        "all_recovery_gains_meet_gate": recovery_pass,
        "min_recovery_gain": min(gains),
        "mean_recovery_gain": sum(gains) / len(gains),
        "co_corruption_control_limit": gates["max_abs_co_corruption_gain"],
        "max_abs_co_corruption_gain": max(co_gains),
        "co_corruption_control_pass": co_control_pass,
        "mean_transition_cost_ratio": sum(cost_ratios) / len(cost_ratios),
        "max_transition_cost_ratio": max(cost_ratios),
        "adaptation_gate_pass": adaptation_pass,
        "phase_planes": 2,
        "auxiliary_stability_counters_per_cell": 1,
        "full_reflective_recovery_gate_pass": (
            recovery_pass and co_control_pass and adaptation_pass
        ),
        "interpretation": (
            "reflection_improves_recovery_without_external_oracle_"
            "but_adds_state_and_transition_cost"
        ),
    }

    report = {
        "schema_version": "cosmic-organics/reflective-result-0.1",
        "suite_id": manifest["suite_id"],
        "parameter_status": "frozen_after_non_evidence_development_probe",
        "confirmation": confirmation,
        "adaptation": adaptation_rows,
        "summary": summary,
    }
    canonical = json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    report["runtime_diagnostic_digest"] = hashlib.sha256(canonical).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rendered = json.dumps(
        run_suite(args.manifest), indent=2, sort_keys=True
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
