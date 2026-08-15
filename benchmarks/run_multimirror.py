"""Frozen confirmation suite for MORPHOS-M2 hierarchical reflection."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.run_reflective import (
    _fixed_binary_targets,
    _flip_binary,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.hierarchical import HierarchicalGrid2D
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw
from morphos.reflective import ReflectiveGrid2D, ReflectiveLaw

DEFAULT_MANIFEST = Path(__file__).with_name("multimirror_manifest.json")


def _m2_law(manifest: dict[str, Any]) -> MultiReflectiveLaw:
    spec = manifest["frozen_m2"]
    return MultiReflectiveLaw(
        local_coupling=spec["local_coupling"],
        domain_coupling=spec["domain_coupling"],
        system_coupling=spec["system_coupling"],
        local_commit_delay=spec["local_commit_delay"],
        domain_commit_delay=spec["domain_commit_delay"],
        system_commit_delay=spec["system_commit_delay"],
    )


def _m1_law(manifest: dict[str, Any]) -> ReflectiveLaw:
    spec = manifest["frozen_m1"]
    return ReflectiveLaw(
        mirror_coupling=spec["mirror_coupling"],
        commit_delay=spec["commit_delay"],
    )


def _corpus_metrics(manifest: dict[str, Any], size: dict[str, Any]) -> dict[str, Any]:
    width = size["width"]
    height = size["height"]
    seed = size["seed"]
    steps = manifest["relax_steps"]
    config, hierarchy = _s2_components(manifest, width, height)
    confirmation = manifest["confirmation"]
    m1_law = _m1_law(manifest)
    m2_law = _m2_law(manifest)

    seeds = _sha_binary_seeds(seed, size["samples"], width * height)
    targets = _fixed_binary_targets(seeds, config, hierarchy, steps)[
        : confirmation["max_targets"]
    ]
    if not targets:
        raise RuntimeError("confirmation corpus produced no binary fixed targets")

    counters = {
        "s2": 0,
        "m1_primary": 0,
        "m1_co": 0,
        "m2_primary": 0,
        "m2_double": 0,
        "m2_domain_only": 0,
        "m2_system_only": 0,
        "m2_all": 0,
    }
    costs = {
        "m1_primary": 0,
        "m1_co": 0,
        "m2_primary": 0,
        "m2_double": 0,
    }
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

            s2 = HierarchicalGrid2D(corrupted, config=config, law=hierarchy)
            s2.run([0.0] * steps)

            m1 = ReflectiveGrid2D(
                target,
                config=config,
                law=hierarchy,
                reflective_law=m1_law,
            )
            m1.perturb_primary([index])
            m1.run([0.0] * steps)

            m1_co = ReflectiveGrid2D(
                target,
                config=config,
                law=hierarchy,
                reflective_law=m1_law,
            )
            m1_co.perturb_primary([index])
            m1_co.perturb_mirror([index])
            m1_co.run([0.0] * steps)

            def m2_case(*corrupted_planes: str) -> MultiReflectiveGrid2D:
                model = MultiReflectiveGrid2D(
                    target,
                    config=config,
                    law=hierarchy,
                    reflective_law=m2_law,
                )
                model.perturb_primary([index])
                if "local" in corrupted_planes:
                    model.perturb_local_mirror([index])
                if "domain" in corrupted_planes:
                    model.perturb_domain_mirror([index])
                if "system" in corrupted_planes:
                    model.perturb_system_mirror([index])
                model.run([0.0] * steps)
                return model

            m2_primary = m2_case()
            m2_double = m2_case("local")
            # Domain-only evidence: local and system mirrors fail with primary.
            m2_domain_only = m2_case("local", "system")
            # System-only evidence: local and domain mirrors fail with primary.
            m2_system_only = m2_case("local", "domain")
            m2_all = m2_case("local", "domain", "system")

            models = {
                "s2": s2,
                "m1_primary": m1,
                "m1_co": m1_co,
                "m2_primary": m2_primary,
                "m2_double": m2_double,
                "m2_domain_only": m2_domain_only,
                "m2_system_only": m2_system_only,
                "m2_all": m2_all,
            }
            for key, model in models.items():
                counters[key] += int(model.state_string() == target)
            costs["m1_primary"] += m1.transitions
            costs["m1_co"] += m1_co.transitions
            costs["m2_primary"] += m2_primary.transitions
            costs["m2_double"] += m2_double.transitions
            trials += 1

    def rate(key: str) -> float:
        return counters[key] / trials

    s2_rate = rate("s2")
    m1_primary_rate = rate("m1_primary")
    m1_co_rate = rate("m1_co")
    m2_primary_rate = rate("m2_primary")
    m2_double_rate = rate("m2_double")
    domain_only_rate = rate("m2_domain_only")
    system_only_rate = rate("m2_system_only")
    all_rate = rate("m2_all")

    return {
        "width": width,
        "height": height,
        "seed": seed,
        "samples": size["samples"],
        "binary_fixed_targets": len(targets),
        "trials": trials,
        "s2_recovery_1bit": s2_rate,
        "m1_primary_recovery_1bit": m1_primary_rate,
        "m1_co_recovery_1bit": m1_co_rate,
        "m2_primary_recovery_1bit": m2_primary_rate,
        "m2_double_recovery_1bit": m2_double_rate,
        "m2_domain_only_recovery_1bit": domain_only_rate,
        "m2_system_only_recovery_1bit": system_only_rate,
        "m2_all_corrupted_recovery_1bit": all_rate,
        "primary_gain_vs_m1": m2_primary_rate - m1_primary_rate,
        "double_gain_vs_m1_co": m2_double_rate - m1_co_rate,
        "domain_only_gain_vs_m1_co": domain_only_rate - m1_co_rate,
        "system_only_gain_vs_m1_co": system_only_rate - m1_co_rate,
        "all_corruption_gain_vs_s2": all_rate - s2_rate,
        "m1_primary_transition_cost": costs["m1_primary"] / trials,
        "m2_primary_transition_cost": costs["m2_primary"] / trials,
        "primary_transition_cost_ratio_vs_m1": (
            costs["m2_primary"] / costs["m1_primary"]
            if costs["m1_primary"]
            else None
        ),
        "m1_co_transition_cost": costs["m1_co"] / trials,
        "m2_double_transition_cost": costs["m2_double"] / trials,
        "double_transition_cost_ratio_vs_m1_co": (
            costs["m2_double"] / costs["m1_co"]
            if costs["m1_co"]
            else None
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
    adaptation = manifest["adaptation"]
    model = MultiReflectiveGrid2D(
        start * (width * height),
        config=config,
        law=hierarchy,
        reflective_law=_m2_law(manifest),
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
        "primary_target_fraction": model.state_string().count(target) / cells,
        "local_mirror_target_fraction": model.local_mirror_string().count(target) / cells,
        "domain_mirror_target_fraction": model.domain_mirror_string().count(target) / cells,
        "system_mirror_target_fraction": model.system_mirror_string().count(target) / cells,
        "transitions": model.transitions,
        "local_mirror_commits": model.local_mirror_commits,
        "domain_mirror_commit_events": model.domain_mirror_commit_events,
        "system_mirror_commit_events": model.system_mirror_commit_events,
    }


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    confirmation = [
        _corpus_metrics(manifest, corpus)
        for corpus in manifest["confirmation"]["corpora"]
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

    gates = manifest["gates"]
    primary_gains = [r["primary_gain_vs_m1"] for r in confirmation]
    double_gains = [r["double_gain_vs_m1_co"] for r in confirmation]
    domain_gains = [r["domain_only_gain_vs_m1_co"] for r in confirmation]
    system_gains = [r["system_only_gain_vs_m1_co"] for r in confirmation]
    all_gains = [abs(r["all_corruption_gain_vs_s2"]) for r in confirmation]
    primary_costs = [
        r["primary_transition_cost_ratio_vs_m1"]
        for r in confirmation
        if r["primary_transition_cost_ratio_vs_m1"] is not None
    ]
    double_costs = [
        r["double_transition_cost_ratio_vs_m1_co"]
        for r in confirmation
        if r["double_transition_cost_ratio_vs_m1_co"] is not None
    ]

    primary_pass = all(
        gain >= gates["minimum_primary_gain_vs_m1"] for gain in primary_gains
    )
    double_pass = all(
        gain >= gates["minimum_double_gain_vs_m1_co"] for gain in double_gains
    )
    domain_pass = all(
        gain >= gates["minimum_domain_only_gain_vs_m1_co"] for gain in domain_gains
    )
    system_pass = all(
        gain >= gates["minimum_system_only_gain_vs_m1_co"] for gain in system_gains
    )
    all_control_pass = all(
        gain <= gates["max_abs_all_corruption_gain_vs_s2"] for gain in all_gains
    )
    adaptation_pass = all(
        row["primary_target_fraction"] == 1.0
        and row["local_mirror_target_fraction"] == 1.0
        and row["domain_mirror_target_fraction"] == 1.0
        and row["system_mirror_target_fraction"] == 1.0
        for row in adaptation_rows
    )

    summary = {
        "confirmation_corpora": len(confirmation),
        "primary_gain_gate_pass": primary_pass,
        "min_primary_gain_vs_m1": min(primary_gains),
        "mean_primary_gain_vs_m1": sum(primary_gains) / len(primary_gains),
        "double_fault_gate_pass": double_pass,
        "min_double_gain_vs_m1_co": min(double_gains),
        "mean_double_gain_vs_m1_co": sum(double_gains) / len(double_gains),
        "domain_only_gate_pass": domain_pass,
        "min_domain_only_gain_vs_m1_co": min(domain_gains),
        "mean_domain_only_gain_vs_m1_co": sum(domain_gains) / len(domain_gains),
        "system_only_gate_pass": system_pass,
        "min_system_only_gain_vs_m1_co": min(system_gains),
        "mean_system_only_gain_vs_m1_co": sum(system_gains) / len(system_gains),
        "all_corruption_control_pass": all_control_pass,
        "max_abs_all_corruption_gain_vs_s2": max(all_gains),
        "adaptation_gate_pass": adaptation_pass,
        "mean_primary_transition_cost_ratio_vs_m1": sum(primary_costs) / len(primary_costs),
        "max_primary_transition_cost_ratio_vs_m1": max(primary_costs),
        "mean_double_transition_cost_ratio_vs_m1_co": sum(double_costs) / len(double_costs),
        "max_double_transition_cost_ratio_vs_m1_co": max(double_costs),
        "phase_planes": 4,
        "full_multimirror_gate_pass": (
            primary_pass
            and double_pass
            and domain_pass
            and system_pass
            and all_control_pass
            and adaptation_pass
        ),
        "interpretation": (
            "hierarchical_reflection_improves_mean_correlated_fault_recovery_"
            "but_strict_cross_corpus_gates_fail"
        ),
    }

    report = {
        "schema_version": "cosmic-organics/multimirror-result-0.1",
        "suite_id": manifest["suite_id"],
        "parameter_status": manifest["frozen_m2"]["parameter_status"],
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
    rendered = json.dumps(run_suite(args.manifest), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
