"""Generalization gate for the frozen 2D heterogeneous MORPHOS candidate."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any, Callable

from benchmarks.recurrent2d import RecurrentBinary2D
from morphos.grid2d import Grid2D, Grid2DConfig

DEFAULT_MANIFEST = Path(__file__).with_name("generalization_manifest.json")


class Majority2D:
    """Binary synchronous majority baseline with configurable neighborhood."""

    def __init__(self, initial: str, *, width: int, height: int, neighborhood: str) -> None:
        if len(initial) != width * height or any(value not in {"A", "C"} for value in initial):
            raise ValueError("Majority2D requires a width*height binary A/C state")
        if neighborhood not in {"von_neumann", "moore"}:
            raise ValueError("unsupported neighborhood")
        self.width = width
        self.height = height
        self.neighborhood = neighborhood
        self.states = list(initial)
        self.transitions = 0

    def _neighbors(self, index: int) -> list[int]:
        row, col = divmod(index, self.width)
        offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if self.neighborhood == "moore":
            offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        result: list[int] = []
        for dr, dc in offsets:
            rr, cc = row + dr, col + dc
            if 0 <= rr < self.height and 0 <= cc < self.width:
                result.append(rr * self.width + cc)
        return result

    def step(self) -> None:
        next_states = self.states.copy()
        for index, current in enumerate(self.states):
            values = [self.states[j] for j in self._neighbors(index)]
            crystalline = values.count("C")
            amorphous = values.count("A")
            if crystalline > amorphous:
                next_states[index] = "C"
            elif amorphous > crystalline:
                next_states[index] = "A"
            else:
                next_states[index] = current
        self.transitions += sum(a != b for a, b in zip(self.states, next_states))
        self.states = next_states

    def run(self, steps: int) -> None:
        for _ in range(steps):
            self.step()

    def state_string(self) -> str:
        return "".join(self.states)


def _sha_binary_seeds(seed: int, samples: int, cells: int) -> list[str]:
    values: list[str] = []
    for sample in range(samples):
        chunks = b""
        counter = 0
        while len(chunks) * 8 < cells:
            chunks += hashlib.sha256(f"{seed}:{sample}:{counter}".encode("ascii")).digest()
            counter += 1
        bits = "".join(f"{byte:08b}" for byte in chunks)[:cells]
        values.append("".join("C" if bit == "1" else "A" for bit in bits))
    return values


def _flip(state: str, indices: tuple[int, ...]) -> str:
    values = list(state)
    for index in indices:
        values[index] = "C" if values[index] == "A" else "A"
    return "".join(values)


def _grid_relax(config: Grid2DConfig, steps: int) -> Callable[[str], tuple[str, int]]:
    def relax(initial: str) -> tuple[str, int]:
        lattice = Grid2D(initial, config=config)
        lattice.run([0.0] * steps)
        return lattice.state_string(), lattice.transitions
    return relax


def _majority_relax(width: int, height: int, steps: int, neighborhood: str) -> Callable[[str], tuple[str, int]]:
    def relax(initial: str) -> tuple[str, int]:
        model = Majority2D(initial, width=width, height=height, neighborhood=neighborhood)
        model.run(steps)
        return model.state_string(), model.transitions
    return relax


def _recurrent_relax(
    width: int,
    height: int,
    steps: int,
    self_weight: float,
    neighbor_weight: float,
) -> Callable[[str], tuple[str, int]]:
    def relax(initial: str) -> tuple[str, int]:
        model = RecurrentBinary2D(
            initial,
            width=width,
            height=height,
            self_weight=self_weight,
            neighbor_weight=neighbor_weight,
        )
        model.run(steps)
        return model.state_string(), model.transitions
    return relax


def _metric_suite(
    seeds: list[str],
    relax: Callable[[str], tuple[str, int]],
    *,
    noise_bits: list[int],
    noise_seed: int,
    trial_cap: int = 1500,
    per_target_combo_cap: int = 12,
) -> dict[str, Any]:
    finals: dict[str, int] = {}
    seed_costs: list[int] = []
    for seed in seeds:
        final_state, transitions = relax(seed)
        finals[final_state] = finals.get(final_state, 0) + 1
        seed_costs.append(transitions)

    fixed: dict[str, int] = {}
    for state, count in finals.items():
        next_state, _ = relax(state)
        if next_state == state:
            fixed[state] = count
    binary_fixed = {state: count for state, count in fixed.items() if "M" not in state}

    report: dict[str, Any] = {
        "binary_capacity_bits": round(math.log2(len(binary_fixed)), 12) if binary_fixed else 0.0,
        "binary_fixed_attractors": len(binary_fixed),
        "binary_fixed_seed_coverage": round(sum(binary_fixed.values()) / len(seeds), 12),
        "fixed_attractors": len(fixed),
        "mixed_fixed_attractors": sum("M" in state for state in fixed),
        "seed_transition_cost": round(sum(seed_costs) / len(seed_costs), 12),
        "unique_final_states": len(finals),
    }

    cells = len(seeds[0])
    targets = list(binary_fixed)
    for bits in noise_bits:
        trials: list[tuple[str, tuple[int, ...]]] = []
        for target_index, target in enumerate(targets):
            combinations = list(itertools.combinations(range(cells), bits))
            if len(combinations) > per_target_combo_cap:
                combinations = sorted(
                    combinations,
                    key=lambda combo: hashlib.sha256(
                        f"{noise_seed}:{target_index}:{bits}:{combo}".encode("ascii")
                    ).digest(),
                )[:per_target_combo_cap]
            trials.extend((target, combo) for combo in combinations)
        if len(trials) > trial_cap:
            trials = sorted(
                trials,
                key=lambda item: hashlib.sha256(
                    f"{noise_seed}:{bits}:{item[0]}:{item[1]}".encode("ascii")
                ).digest(),
            )[:trial_cap]

        recovered = 0
        recovery_costs: list[int] = []
        for target, indices in trials:
            final_state, transitions = relax(_flip(target, indices))
            recovered += int(final_state == target)
            recovery_costs.append(transitions)
        report[f"recovery_{bits}bit"] = round(recovered / len(trials), 12) if trials else 0.0
        report[f"recovery_cost_{bits}bit"] = round(sum(recovery_costs) / len(recovery_costs), 12) if trials else 0.0
        report[f"recovery_trials_{bits}bit"] = len(trials)

    return report


def _candidate_config(spec: dict[str, Any], *, width: int, height: int, mask: str | None = None, neighborhood: str | None = None) -> Grid2DConfig:
    values = dict(spec)
    if mask is not None:
        values["mask"] = mask
    if neighborhood is not None:
        values["neighborhood"] = neighborhood
    return Grid2DConfig(width=width, height=height, **values)


def _compare(candidate: dict[str, Any], baseline: dict[str, Any], bits: int = 1) -> dict[str, Any]:
    baseline_seed_cost = baseline["seed_transition_cost"]
    baseline_recovery_cost = baseline[f"recovery_cost_{bits}bit"]
    return {
        "binary_capacity_delta_bits": round(candidate["binary_capacity_bits"] - baseline["binary_capacity_bits"], 12),
        "binary_coverage_delta": round(candidate["binary_fixed_seed_coverage"] - baseline["binary_fixed_seed_coverage"], 12),
        "recovery_delta": round(candidate[f"recovery_{bits}bit"] - baseline[f"recovery_{bits}bit"], 12),
        "recovery_cost_ratio": round(candidate[f"recovery_cost_{bits}bit"] / baseline_recovery_cost, 12) if baseline_recovery_cost else None,
        "seed_cost_ratio": round(candidate["seed_transition_cost"] / baseline_seed_cost, 12) if baseline_seed_cost else None,
    }


def _dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    better_or_equal = (
        a["binary_capacity_bits"] >= b["binary_capacity_bits"]
        and a["recovery_1bit"] >= b["recovery_1bit"]
        and a["seed_transition_cost"] <= b["seed_transition_cost"]
    )
    strict = (
        a["binary_capacity_bits"] > b["binary_capacity_bits"]
        or a["recovery_1bit"] > b["recovery_1bit"]
        or a["seed_transition_cost"] < b["seed_transition_cost"]
    )
    return better_or_equal and strict


def _evaluate_pair(
    candidate_spec: dict[str, Any],
    *,
    width: int,
    height: int,
    seed: int,
    samples: int,
    steps: int,
    mask: str | None = None,
    neighborhood: str | None = None,
    noise_bits: list[int] | None = None,
    trial_cap: int = 1500,
    per_target_combo_cap: int = 12,
) -> dict[str, Any]:
    selected_neighborhood = neighborhood or candidate_spec["neighborhood"]
    config = _candidate_config(candidate_spec, width=width, height=height, mask=mask, neighborhood=selected_neighborhood)
    seeds = _sha_binary_seeds(seed, samples, width * height)
    bits = noise_bits or [1]
    candidate = _metric_suite(
        seeds,
        _grid_relax(config, steps),
        noise_bits=bits,
        noise_seed=seed,
        trial_cap=trial_cap,
        per_target_combo_cap=per_target_combo_cap,
    )
    majority = _metric_suite(
        seeds,
        _majority_relax(width, height, steps, selected_neighborhood),
        noise_bits=bits,
        noise_seed=seed,
        trial_cap=trial_cap,
        per_target_combo_cap=per_target_combo_cap,
    )
    comparisons = {f"{value}bit": _compare(candidate, majority, value) for value in bits}
    return {
        "candidate": candidate,
        "majority_ca": majority,
        "comparison": comparisons,
        "height": height,
        "samples": samples,
        "seed": seed,
        "width": width,
    }


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 12)


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_spec = manifest["frozen_candidate"]
    steps = manifest["relax_steps"]

    multi_spec = manifest["multi_seed"]
    multi_results = [
        _evaluate_pair(
            candidate_spec,
            width=multi_spec["width"],
            height=multi_spec["height"],
            seed=seed,
            samples=multi_spec["samples"],
            steps=steps,
        )
        for seed in multi_spec["seeds"]
    ]
    multi_capacity = [item["comparison"]["1bit"]["binary_capacity_delta_bits"] for item in multi_results]
    multi_recovery = [item["comparison"]["1bit"]["recovery_delta"] for item in multi_results]
    multi_cost = [item["comparison"]["1bit"]["seed_cost_ratio"] for item in multi_results]
    multi_summary = {
        "all_capacity_deltas_positive": all(value > 0 for value in multi_capacity),
        "all_recovery_deltas_negative": all(value < 0 for value in multi_recovery),
        "all_seed_cost_ratios_below_one": all(value is not None and value < 1 for value in multi_cost),
        "mean_capacity_delta_bits": _mean(multi_capacity),
        "mean_recovery_delta": _mean(multi_recovery),
        "mean_seed_cost_ratio": _mean([value for value in multi_cost if value is not None]),
        "seed_transfer_gate_pass": all(value > 0 for value in multi_capacity) and all(value is not None and value < 1 for value in multi_cost),
    }

    scale_results = [
        _evaluate_pair(
            candidate_spec,
            width=item["width"],
            height=item["height"],
            seed=item["seed"],
            samples=item["samples"],
            steps=steps,
        )
        for item in manifest["scale"]
    ]
    scale_summary = {
        "capacity_advantage_sizes": [item["width"] for item in scale_results if item["comparison"]["1bit"]["binary_capacity_delta_bits"] > 0],
        "scaling_gate_pass": all(item["comparison"]["1bit"]["binary_capacity_delta_bits"] > 0 for item in scale_results),
    }

    mask_spec = manifest["mask_ablation"]
    mask_results: dict[str, Any] = {}
    for mask in mask_spec["masks"]:
        mask_results[mask] = _evaluate_pair(
            candidate_spec,
            width=mask_spec["width"],
            height=mask_spec["height"],
            seed=mask_spec["seed"],
            samples=mask_spec["samples"],
            steps=steps,
            mask=mask,
        )

    neighborhood_spec = manifest["neighborhood_ablation"]
    neighborhood_results: dict[str, Any] = {}
    for neighborhood in neighborhood_spec["neighborhoods"]:
        neighborhood_results[neighborhood] = _evaluate_pair(
            candidate_spec,
            width=neighborhood_spec["width"],
            height=neighborhood_spec["height"],
            seed=neighborhood_spec["seed"],
            samples=neighborhood_spec["samples"],
            steps=steps,
            neighborhood=neighborhood,
        )

    noise_spec = manifest["multi_bit_noise"]
    multi_bit_result = _evaluate_pair(
        candidate_spec,
        width=noise_spec["width"],
        height=noise_spec["height"],
        seed=noise_spec["seed"],
        samples=noise_spec["samples"],
        steps=steps,
        noise_bits=noise_spec["bits"],
        trial_cap=noise_spec["trial_cap"],
        per_target_combo_cap=noise_spec["per_target_combo_cap"],
    )
    multi_bit_summary = {
        "candidate_recovery_above_majority_for_all_bits": all(
            multi_bit_result["comparison"][f"{bits}bit"]["recovery_delta"] >= 0
            for bits in noise_spec["bits"]
        ),
        "candidate_recovery_cost_below_majority_for_all_bits": all(
            multi_bit_result["comparison"][f"{bits}bit"]["recovery_cost_ratio"] is not None
            and multi_bit_result["comparison"][f"{bits}bit"]["recovery_cost_ratio"] < 1
            for bits in noise_spec["bits"]
        ),
    }

    recurrent_spec = manifest["recurrent_challenge"]
    discovery_seeds = _sha_binary_seeds(
        recurrent_spec["discovery_seed"],
        recurrent_spec["discovery_samples"],
        recurrent_spec["width"] * recurrent_spec["height"],
    )
    recurrent_points: list[dict[str, Any]] = []
    for self_weight in recurrent_spec["self_weights"]:
        for neighbor_weight in recurrent_spec["neighbor_weights"]:
            metrics = _metric_suite(
                discovery_seeds,
                _recurrent_relax(
                    recurrent_spec["width"],
                    recurrent_spec["height"],
                    steps,
                    self_weight,
                    neighbor_weight,
                ),
                noise_bits=[1],
                noise_seed=recurrent_spec["discovery_seed"],
            )
            recurrent_points.append({
                "self_weight": self_weight,
                "neighbor_weight": neighbor_weight,
                "metrics": metrics,
            })

    unique_by_signature: dict[tuple[Any, ...], dict[str, Any]] = {}
    for point in recurrent_points:
        metrics = point["metrics"]
        signature = (
            metrics["binary_capacity_bits"],
            metrics["binary_fixed_seed_coverage"],
            metrics["recovery_1bit"],
            metrics["recovery_cost_1bit"],
            metrics["seed_transition_cost"],
        )
        unique_by_signature.setdefault(signature, point)
    unique_regimes = list(unique_by_signature.values())

    confirmation_seeds = _sha_binary_seeds(
        recurrent_spec["confirmation_seed"],
        recurrent_spec["confirmation_samples"],
        recurrent_spec["width"] * recurrent_spec["height"],
    )
    frozen_config = _candidate_config(
        candidate_spec,
        width=recurrent_spec["width"],
        height=recurrent_spec["height"],
    )
    candidate_confirmation = _metric_suite(
        confirmation_seeds,
        _grid_relax(frozen_config, steps),
        noise_bits=[1],
        noise_seed=recurrent_spec["confirmation_seed"],
    )
    recurrent_confirmation: list[dict[str, Any]] = []
    for regime in unique_regimes:
        metrics = _metric_suite(
            confirmation_seeds,
            _recurrent_relax(
                recurrent_spec["width"],
                recurrent_spec["height"],
                steps,
                regime["self_weight"],
                regime["neighbor_weight"],
            ),
            noise_bits=[1],
            noise_seed=recurrent_spec["confirmation_seed"],
        )
        recurrent_confirmation.append({
            "self_weight": regime["self_weight"],
            "neighbor_weight": regime["neighbor_weight"],
            "metrics": metrics,
            "dominates_candidate": _dominates(metrics, candidate_confirmation),
            "candidate_dominates": _dominates(candidate_confirmation, metrics),
        })

    recurrent_summary = {
        "discovery_parameter_points": len(recurrent_points),
        "discovery_unique_regimes": len(unique_regimes),
        "candidate_pareto_nondominated_on_confirmation": not any(item["dominates_candidate"] for item in recurrent_confirmation),
        "candidate_fully_dominates_recurrent_frontier": all(item["candidate_dominates"] for item in recurrent_confirmation),
    }

    summary = {
        "seed_transfer_gate_pass": multi_summary["seed_transfer_gate_pass"],
        "scaling_gate_pass": scale_summary["scaling_gate_pass"],
        "multi_bit_recovery_gate_pass": multi_bit_summary["candidate_recovery_above_majority_for_all_bits"],
        "multi_bit_cost_gate_pass": multi_bit_summary["candidate_recovery_cost_below_majority_for_all_bits"],
        "recurrent_pareto_gate_pass": recurrent_summary["candidate_pareto_nondominated_on_confirmation"],
    }
    summary["full_generalization_gate_pass"] = all(summary.values())
    summary["interpretation"] = "partial_seed_transfer_new_pareto_not_scale_generalization"

    report: dict[str, Any] = {
        "frozen_candidate": candidate_spec,
        "mask_ablation": mask_results,
        "multi_bit_noise": {
            "result": multi_bit_result,
            "summary": multi_bit_summary,
        },
        "multi_seed": {
            "results": multi_results,
            "summary": multi_summary,
        },
        "neighborhood_ablation": neighborhood_results,
        "recurrent_challenge": {
            "candidate_confirmation": candidate_confirmation,
            "confirmation_regimes": recurrent_confirmation,
            "discovery_unique_regimes": unique_regimes,
            "summary": recurrent_summary,
        },
        "scale": {
            "results": scale_results,
            "summary": scale_summary,
        },
        "schema_version": "cosmic-organics/generalization-result-0.1",
        "suite_id": manifest["suite_id"],
        "summary": summary,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    report["result_digest"] = hashlib.sha256(canonical).hexdigest()
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
