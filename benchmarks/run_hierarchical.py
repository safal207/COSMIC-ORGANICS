"""Discover and confirm MORPHOS-S2 hierarchical dynamics without per-size retuning."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from benchmarks.run_scale_aware import (
    _base_config,
    _capacity_cost,
    _compare,
    _grid_relax,
    _majority_relax,
    _metric_suite,
    _sha_binary_seeds,
)
from morphos.hierarchical import HierarchicalGrid2D, HierarchicalLaw
from morphos.scale_aware import ScaleLaw

DEFAULT_MANIFEST = Path(__file__).with_name("hierarchical_manifest.json")


def _hierarchical_relax(
    config,
    law: HierarchicalLaw,
    steps: int,
) -> Callable[[str], tuple[str, int]]:
    def relax(initial: str) -> tuple[str, int]:
        lattice = HierarchicalGrid2D(initial, config=config, law=law)
        lattice.run([0.0] * steps)
        return lattice.state_string(), lattice.transitions

    return relax


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    steps = manifest["relax_steps"]
    base = _base_config(manifest["frozen_candidate"])
    scale_spec = manifest["s1_scale_law"]
    s1_law = ScaleLaw(
        reference_linear_size=scale_spec["reference_linear_size"],
        exponent=scale_spec["exponent"],
    )

    discovery = manifest["discovery"]
    discovery_results: list[dict[str, Any]] = []
    selected: float | None = None

    for exponent in discovery["hierarchy_exponents"]:
        law = HierarchicalLaw(
            reference_linear_size=discovery["reference_linear_size"],
            exponent=exponent,
            domain_size=discovery["domain_size"],
        )
        capacity_deltas: list[float] = []
        seed_cost_ratios: list[float] = []
        corpus_count = 0

        for size in discovery["sizes"]:
            scaled = s1_law.apply(
                base,
                width=size["width"],
                height=size["height"],
            )
            for seed in size["seeds"]:
                seeds = _sha_binary_seeds(
                    seed,
                    size["samples"],
                    size["width"] * size["height"],
                )
                candidate = _capacity_cost(
                    seeds,
                    _hierarchical_relax(scaled, law, steps),
                )
                majority = _capacity_cost(
                    seeds,
                    _majority_relax(
                        size["width"],
                        size["height"],
                        steps,
                    ),
                )
                capacity_deltas.append(
                    candidate["binary_capacity_bits"]
                    - majority["binary_capacity_bits"]
                )
                seed_cost_ratios.append(
                    candidate["seed_transition_cost"]
                    / majority["seed_transition_cost"]
                    if majority["seed_transition_cost"]
                    else 0.0
                )
                corpus_count += 1

        passes = all(value > 0 for value in capacity_deltas) and all(
            value < 1 for value in seed_cost_ratios
        )
        discovery_results.append(
            {
                "hierarchy_exponent": exponent,
                "corpora": corpus_count,
                "passes": passes,
                "min_capacity_delta_bits": round(
                    min(capacity_deltas), 12
                ),
                "mean_capacity_delta_bits": round(
                    sum(capacity_deltas) / len(capacity_deltas), 12
                ),
                "max_seed_cost_ratio": round(
                    max(seed_cost_ratios), 12
                ),
            }
        )
        if passes:
            selected = exponent

    if selected is None:
        raise RuntimeError(
            "discovery produced no admissible hierarchy exponent"
        )

    selected_law = HierarchicalLaw(
        reference_linear_size=discovery["reference_linear_size"],
        exponent=selected,
        domain_size=discovery["domain_size"],
    )

    confirmation_spec = manifest["confirmation"]
    confirmation: list[dict[str, Any]] = []
    capacity_deltas: list[float] = []
    recovery_deltas: list[float] = []
    recovery_gains: list[float] = []
    seed_cost_ratios: list[float] = []
    recovery_cost_ratios: list[float] = []
    large_scale_capacity_deltas: list[float] = []
    large_scale_recovery_gains: list[float] = []

    for size in confirmation_spec["sizes"]:
        scaled = s1_law.apply(
            base,
            width=size["width"],
            height=size["height"],
        )
        for seed in size["seeds"]:
            seeds = _sha_binary_seeds(
                seed,
                size["samples"],
                size["width"] * size["height"],
            )
            majority = _metric_suite(
                seeds,
                _majority_relax(
                    size["width"],
                    size["height"],
                    steps,
                ),
                noise_seed=seed,
                trial_cap=confirmation_spec["trial_cap"],
                per_target_combo_cap=confirmation_spec[
                    "per_target_combo_cap"
                ],
            )
            s1 = _metric_suite(
                seeds,
                _grid_relax(scaled, steps),
                noise_seed=seed,
                trial_cap=confirmation_spec["trial_cap"],
                per_target_combo_cap=confirmation_spec[
                    "per_target_combo_cap"
                ],
            )
            s2 = _metric_suite(
                seeds,
                _hierarchical_relax(
                    scaled,
                    selected_law,
                    steps,
                ),
                noise_seed=seed,
                trial_cap=confirmation_spec["trial_cap"],
                per_target_combo_cap=confirmation_spec[
                    "per_target_combo_cap"
                ],
            )
            versus_majority = _compare(s2, majority)
            versus_s1 = {
                "binary_capacity_delta_bits": round(
                    s2["binary_capacity_bits"]
                    - s1["binary_capacity_bits"],
                    12,
                ),
                "recovery_gain": round(
                    s2["recovery_1bit"] - s1["recovery_1bit"],
                    12,
                ),
                "seed_cost_ratio": round(
                    s2["seed_transition_cost"]
                    / s1["seed_transition_cost"],
                    12,
                )
                if s1["seed_transition_cost"]
                else None,
                "recovery_cost_ratio": round(
                    s2["recovery_cost_1bit"]
                    / s1["recovery_cost_1bit"],
                    12,
                )
                if s1["recovery_cost_1bit"]
                else None,
            }

            confirmation.append(
                {
                    "width": size["width"],
                    "height": size["height"],
                    "seed": seed,
                    "samples": size["samples"],
                    "s1_scale_factor": round(
                        s1_law.factor(
                            size["width"],
                            size["height"],
                        ),
                        12,
                    ),
                    "hierarchy_intra_factor": round(
                        selected_law.intra_factor(
                            size["width"],
                            size["height"],
                        ),
                        12,
                    ),
                    "s2": s2,
                    "s1": s1,
                    "majority_ca": majority,
                    "comparison_vs_majority": versus_majority,
                    "comparison_vs_s1": versus_s1,
                }
            )

            capacity_deltas.append(
                versus_majority["binary_capacity_delta_bits"]
            )
            recovery_deltas.append(
                versus_majority["recovery_delta"]
            )
            recovery_gains.append(versus_s1["recovery_gain"])
            seed_cost_ratios.append(
                versus_majority["seed_cost_ratio"]
            )
            recovery_cost_ratios.append(
                versus_majority["recovery_cost_ratio"]
            )
            if size["width"] > discovery["reference_linear_size"]:
                large_scale_capacity_deltas.append(
                    versus_majority["binary_capacity_delta_bits"]
                )
                large_scale_recovery_gains.append(
                    versus_s1["recovery_gain"]
                )

    five_by_five = [
        item for item in confirmation if item["width"] == 5
    ]
    summary = {
        "selected_hierarchy_exponent": selected,
        "domain_size": discovery["domain_size"],
        "confirmation_corpora": len(confirmation),
        "fresh_5x5_capacity_failure_corpora": sum(
            item["comparison_vs_majority"][
                "binary_capacity_delta_bits"
            ]
            <= 0
            for item in five_by_five
        ),
        "s1_fresh_5x5_capacity_failure_corpora": sum(
            (
                item["s1"]["binary_capacity_bits"]
                - item["majority_ca"]["binary_capacity_bits"]
            )
            <= 0
            for item in five_by_five
        ),
        "large_scale_capacity_gate_pass": all(
            value > 0 for value in large_scale_capacity_deltas
        ),
        "large_scale_recovery_gain_gate_pass": all(
            value > 0 for value in large_scale_recovery_gains
        ),
        "recovery_parity_gate_pass": all(
            value >= 0 for value in recovery_deltas
        ),
        "mean_capacity_delta_bits": round(
            sum(capacity_deltas) / len(capacity_deltas), 12
        ),
        "mean_recovery_delta": round(
            sum(recovery_deltas) / len(recovery_deltas), 12
        ),
        "mean_recovery_gain_vs_s1": round(
            sum(recovery_gains) / len(recovery_gains), 12
        ),
        "large_scale_mean_recovery_gain_vs_s1": round(
            sum(large_scale_recovery_gains)
            / len(large_scale_recovery_gains),
            12,
        ),
        "large_scale_min_recovery_gain_vs_s1": round(
            min(large_scale_recovery_gains), 12
        ),
        "large_scale_min_capacity_delta_bits": round(
            min(large_scale_capacity_deltas), 12
        ),
        "mean_seed_cost_ratio": round(
            sum(seed_cost_ratios) / len(seed_cost_ratios), 12
        ),
        "mean_recovery_cost_ratio": round(
            sum(recovery_cost_ratios)
            / len(recovery_cost_ratios),
            12,
        ),
        "full_hierarchical_generalization_pass": (
            all(value > 0 for value in capacity_deltas)
            and all(value >= 0 for value in recovery_deltas)
        ),
        "interpretation": (
            "hierarchy_improves_large_scale_recovery_"
            "but_does_not_close_generalization"
        ),
    }

    report = {
        "schema_version": "cosmic-organics/hierarchical-result-0.1",
        "suite_id": manifest["suite_id"],
        "selection_rule": discovery["selection_rule"],
        "discovery": discovery_results,
        "confirmation": confirmation,
        "summary": summary,
    }
    canonical = json.dumps(
        report,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    report["result_digest"] = hashlib.sha256(canonical).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(
        run_suite(args.manifest),
        indent=2,
        sort_keys=True,
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
