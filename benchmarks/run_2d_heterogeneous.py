"""Evaluate a frozen 2D checkerboard-heterogeneous MORPHOS candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

from morphos.grid2d import Grid2D, Grid2DConfig

DEFAULT_MANIFEST = Path(__file__).with_name("heterogeneous_2d_manifest.json")


class Majority2D:
    def __init__(self, initial: str, *, width: int, height: int) -> None:
        if len(initial) != width * height or any(value not in {"A", "C"} for value in initial):
            raise ValueError("Majority2D requires a width*height binary A/C state")
        self.width = width
        self.height = height
        self.states = list(initial)
        self.transitions = 0

    def _neighbors(self, index: int) -> list[int]:
        row, col = divmod(index, self.width)
        values: list[int] = []
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rr, cc = row + dr, col + dc
            if 0 <= rr < self.height and 0 <= cc < self.width:
                values.append(rr * self.width + cc)
        return values

    def step(self) -> None:
        next_states = self.states.copy()
        for index, current in enumerate(self.states):
            neighbors = [self.states[j] for j in self._neighbors(index)]
            crystalline = neighbors.count("C")
            amorphous = neighbors.count("A")
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


def _flatten(rows: list[str]) -> str:
    return "".join(rows)


def _flip(value: str, index: int) -> str:
    replacement = "C" if value[index] == "A" else "A"
    return value[:index] + replacement + value[index + 1 :]


def _grid_relax(config: Grid2DConfig, steps: int) -> Callable[[str], tuple[str, int]]:
    def relax(initial: str) -> tuple[str, int]:
        lattice = Grid2D(initial, config=config)
        lattice.run([0.0] * steps)
        return lattice.state_string(), lattice.transitions
    return relax


def _majority_relax(width: int, height: int, steps: int) -> Callable[[str], tuple[str, int]]:
    def relax(initial: str) -> tuple[str, int]:
        model = Majority2D(initial, width=width, height=height)
        model.run(steps)
        return model.state_string(), model.transitions
    return relax


def _structured_metrics(patterns: dict[str, str], relax: Callable[[str], tuple[str, int]]) -> dict[str, Any]:
    stable = [name for name, pattern in patterns.items() if relax(pattern)[0] == pattern]
    recovered = 0
    trials = 0
    costs: list[int] = []
    for name in stable:
        pattern = patterns[name]
        for index in range(len(pattern)):
            final_state, transitions = relax(_flip(pattern, index))
            recovered += int(final_state == pattern)
            trials += 1
            costs.append(transitions)
    return {
        "stable_patterns": stable,
        "stable_pattern_count": len(stable),
        "one_bit_recovery_rate": round(recovered / trials, 12) if trials else 0.0,
        "average_recovery_transition_cost": round(sum(costs) / len(costs), 12) if costs else 0.0,
    }


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


def _confirmation_metrics(seeds: list[str], relax: Callable[[str], tuple[str, int]]) -> dict[str, Any]:
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
    recovered = 0
    trials = 0
    recovery_costs: list[int] = []
    for target in binary_fixed:
        for index in range(len(target)):
            final_state, transitions = relax(_flip(target, index))
            recovered += int(final_state == target)
            trials += 1
            recovery_costs.append(transitions)

    return {
        "unique_final_states": len(finals),
        "fixed_attractors": len(fixed),
        "binary_fixed_attractors": len(binary_fixed),
        "fixed_seed_coverage": round(sum(fixed.values()) / len(seeds), 12),
        "binary_fixed_seed_coverage": round(sum(binary_fixed.values()) / len(seeds), 12),
        "binary_capacity_bits": round(math.log2(len(binary_fixed)), 12) if binary_fixed else 0.0,
        "one_bit_recovery": round(recovered / trials, 12) if trials else 0.0,
        "recovery_cost": round(sum(recovery_costs) / len(recovery_costs), 12) if recovery_costs else 0.0,
        "seed_transition_cost": round(sum(seed_costs) / len(seed_costs), 12),
        "mixed_fixed_attractors": sum("M" in state for state in fixed),
        "recovery_trials": trials,
    }


def _dominates(a: dict[str, Any], b: dict[str, Any]) -> bool:
    better_or_equal = (
        a["binary_capacity_bits"] >= b["binary_capacity_bits"]
        and a["one_bit_recovery"] >= b["one_bit_recovery"]
        and a["binary_fixed_seed_coverage"] >= b["binary_fixed_seed_coverage"]
        and a["recovery_cost"] <= b["recovery_cost"]
    )
    strict = (
        a["binary_capacity_bits"] > b["binary_capacity_bits"]
        or a["one_bit_recovery"] > b["one_bit_recovery"]
        or a["binary_fixed_seed_coverage"] > b["binary_fixed_seed_coverage"]
        or a["recovery_cost"] < b["recovery_cost"]
    )
    return better_or_equal and strict


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    width = manifest["grid"]["width"]
    height = manifest["grid"]["height"]
    cells = width * height

    candidate = Grid2DConfig(width=width, height=height, **manifest["candidate"])
    anchor = Grid2DConfig(
        width=width, height=height, memory_decay=candidate.memory_decay,
        anchor_threshold=candidate.anchor_threshold, adaptive_threshold=candidate.anchor_threshold,
        anchor_coupling=candidate.anchor_coupling, adaptive_coupling=candidate.anchor_coupling,
        mixed_relax_threshold=candidate.mixed_relax_threshold, mask="checkerboard",
    )
    adaptive = Grid2DConfig(
        width=width, height=height, memory_decay=candidate.memory_decay,
        anchor_threshold=candidate.adaptive_threshold, adaptive_threshold=candidate.adaptive_threshold,
        anchor_coupling=candidate.adaptive_coupling, adaptive_coupling=candidate.adaptive_coupling,
        mixed_relax_threshold=candidate.mixed_relax_threshold, mask="checkerboard",
    )

    structured_patterns = {item["id"]: _flatten(item["rows"]) for item in manifest["structured"]["patterns"]}
    structured_steps = manifest["structured"]["relax_steps"]
    structured = {
        "majority_ca": _structured_metrics(structured_patterns, _majority_relax(width, height, structured_steps)),
        "heterogeneous_checkerboard": _structured_metrics(structured_patterns, _grid_relax(candidate, structured_steps)),
        "homogeneous_anchor": _structured_metrics(structured_patterns, _grid_relax(anchor, structured_steps)),
        "homogeneous_adaptive": _structured_metrics(structured_patterns, _grid_relax(adaptive, structured_steps)),
    }

    confirmation_spec = manifest["confirmation"]
    seeds = _sha_binary_seeds(confirmation_spec["seed"], confirmation_spec["samples"], cells)
    confirmation_steps = confirmation_spec["relax_steps"]
    confirmation = {
        "majority_ca": _confirmation_metrics(seeds, _majority_relax(width, height, confirmation_steps)),
        "heterogeneous_checkerboard": _confirmation_metrics(seeds, _grid_relax(candidate, confirmation_steps)),
        "homogeneous_anchor": _confirmation_metrics(seeds, _grid_relax(anchor, confirmation_steps)),
        "homogeneous_adaptive": _confirmation_metrics(seeds, _grid_relax(adaptive, confirmation_steps)),
    }

    hetero = confirmation["heterogeneous_checkerboard"]
    majority = confirmation["majority_ca"]
    others = [confirmation["majority_ca"], confirmation["homogeneous_anchor"], confirmation["homogeneous_adaptive"]]

    report: dict[str, Any] = {
        "confirmation": confirmation,
        "schema_version": "cosmic-organics/2d-heterogeneous-result-0.1",
        "selection_provenance": manifest["selection_provenance"],
        "structured": structured,
        "suite_id": manifest["suite_id"],
        "summary": {
            "structured_same_codebook_more_recovery_lower_cost": (
                structured["heterogeneous_checkerboard"]["stable_pattern_count"] == structured["majority_ca"]["stable_pattern_count"]
                and structured["heterogeneous_checkerboard"]["one_bit_recovery_rate"] > structured["majority_ca"]["one_bit_recovery_rate"]
                and structured["heterogeneous_checkerboard"]["average_recovery_transition_cost"] < structured["majority_ca"]["average_recovery_transition_cost"]
            ),
            "confirmation_candidate_binary_capacity_delta_bits_vs_majority": round(hetero["binary_capacity_bits"] - majority["binary_capacity_bits"], 12),
            "confirmation_candidate_recovery_delta_vs_majority": round(hetero["one_bit_recovery"] - majority["one_bit_recovery"], 12),
            "confirmation_candidate_binary_coverage_delta_vs_majority": round(hetero["binary_fixed_seed_coverage"] - majority["binary_fixed_seed_coverage"], 12),
            "confirmation_candidate_recovery_cost_ratio_vs_majority": round(hetero["recovery_cost"] / majority["recovery_cost"], 12),
            "confirmation_candidate_seed_cost_ratio_vs_majority": round(hetero["seed_transition_cost"] / majority["seed_transition_cost"], 12),
            "candidate_pareto_nondominated": not any(_dominates(other, hetero) for other in others),
            "full_dominance_observed": all(not _dominates(other, hetero) for other in others) and all(_dominates(hetero, other) for other in others),
            "interpretation": "new_pareto_point_not_full_dominance",
        },
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
