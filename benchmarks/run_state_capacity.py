"""Measure binary state capacity, retention, noise recovery, and transition cost."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any, Callable

from benchmarks.external_baselines import MajorityCA
from morphos.simulator import Phase
from morphos.temporal import TemporalConfig, TemporalLattice

DEFAULT_MANIFEST = Path(__file__).with_name("state_capacity_manifest.json")


def _patterns(size: int) -> list[str]:
    return ["".join(values) for values in itertools.product("AC", repeat=size)]


def _phases(value: str) -> list[Phase]:
    return [Phase(char) for char in value]


def _flip(value: str, index: int) -> str:
    replacement = "C" if value[index] == "A" else "A"
    return value[:index] + replacement + value[index + 1 :]


def _morphos_relax(value: str, config: TemporalConfig, steps: int) -> tuple[str, int]:
    lattice = TemporalLattice(size=len(value), initial=_phases(value), config=config)
    lattice.run([0.0] * steps)
    return lattice.phase_string(), lattice.transition_count


def _majority_relax(value: str, steps: int) -> tuple[str, int]:
    model = MajorityCA(value)
    model.run(steps)
    return model.state_string(), model.transitions


def _capacity_metrics(
    patterns: list[str],
    relax: Callable[[str], tuple[str, int]],
    *,
    mixed_states_possible: bool,
) -> dict[str, Any]:
    stable = [pattern for pattern in patterns if relax(pattern)[0] == pattern]
    recovered = 0
    corruption_trials = 0
    transition_costs: list[int] = []
    mixed_dead_zones = 0

    for target in stable:
        for index in range(len(target)):
            corrupted = _flip(target, index)
            final_state, transitions = relax(corrupted)
            corruption_trials += 1
            recovered += int(final_state == target)
            transition_costs.append(transitions)
            if mixed_states_possible and "M" in final_state:
                mixed_dead_zones += 1

    stable_count = len(stable)
    return {
        "stable_states": stable_count,
        "stable_fraction": round(stable_count / len(patterns), 12),
        "capacity_bits": round(math.log2(stable_count), 12) if stable_count else 0.0,
        "corruption_trials": corruption_trials,
        "one_bit_recovery_rate": round(recovered / corruption_trials, 12)
        if corruption_trials
        else 0.0,
        "average_relaxation_transition_cost": round(
            sum(transition_costs) / len(transition_costs), 12
        )
        if transition_costs
        else 0.0,
        "mixed_dead_zone_fraction": round(mixed_dead_zones / corruption_trials, 12)
        if corruption_trials
        else 0.0,
    }


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    size = int(manifest["lattice_size"])
    steps = int(manifest["relax_steps"])
    patterns = _patterns(size)
    fixed = manifest["fixed_config"]

    morphos_sweep: list[dict[str, Any]] = []
    for coupling in manifest["coupling_sweep"]:
        config = TemporalConfig(coupling=float(coupling), **fixed)
        metrics = _capacity_metrics(
            patterns,
            lambda value, config=config: _morphos_relax(value, config, steps),
            mixed_states_possible=True,
        )
        morphos_sweep.append({"coupling": float(coupling), **metrics})

    independent = {
        "kind": "independent_binary_memory",
        "stable_states": len(patterns),
        "stable_fraction": 1.0,
        "capacity_bits": round(math.log2(len(patterns)), 12),
        "corruption_trials": len(patterns) * size,
        "one_bit_recovery_rate": 0.0,
        "average_relaxation_transition_cost": 0.0,
        "mixed_dead_zone_fraction": 0.0,
    }

    majority = {
        "kind": "majority_ca",
        **_capacity_metrics(
            patterns,
            lambda value: _majority_relax(value, steps),
            mixed_states_possible=False,
        ),
    }

    robust = next(
        item
        for item in morphos_sweep
        if item["coupling"] == float(manifest["robust_config_coupling"])
    )

    report: dict[str, Any] = {
        "baselines": [independent, majority],
        "morphos_sweep": morphos_sweep,
        "schema_version": "cosmic-organics/state-capacity-result-0.1",
        "suite_id": manifest["suite_id"],
        "summary": {
            "capacity_advantage_observed": robust["capacity_bits"]
            > max(independent["capacity_bits"], majority["capacity_bits"]),
            "noise_advantage_observed": robust["one_bit_recovery_rate"]
            > majority["one_bit_recovery_rate"],
            "mixed_dead_zone_detected": robust["mixed_dead_zone_fraction"] > 0.0,
            "robust_config": {
                "coupling": robust["coupling"],
                "stable_states": robust["stable_states"],
                "capacity_bits": robust["capacity_bits"],
                "one_bit_recovery_rate": robust["one_bit_recovery_rate"],
                "mixed_dead_zone_fraction": robust["mixed_dead_zone_fraction"],
            },
            "majority_ca": {
                "stable_states": majority["stable_states"],
                "capacity_bits": majority["capacity_bits"],
                "one_bit_recovery_rate": majority["one_bit_recovery_rate"],
            },
            "independent_memory": {
                "stable_states": independent["stable_states"],
                "capacity_bits": independent["capacity_bits"],
                "one_bit_recovery_rate": independent["one_bit_recovery_rate"],
            },
        },
    }
    canonical = json.dumps(
        report, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
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
