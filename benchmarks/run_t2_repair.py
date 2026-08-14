"""Evaluate MORPHOS-T2 mixed-state repair against locked P1 gates and capacity."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any

from benchmarks.external_baselines import MajorityCA
from morphos.simulator import Phase
from morphos.temporal_t2 import T2Config, T2Lattice

DEFAULT_MANIFEST = Path(__file__).with_name("t2_repair_manifest.json")
ROBUSTNESS_MANIFEST = Path(__file__).with_name("robustness_manifest.json")


def _phases(value: str) -> list[Phase]:
    return [Phase(char) for char in value]


def _run(
    initial: str,
    pulses: list[float],
    *,
    memory_decay: float,
    threshold: float,
    coupling: float,
    mixed_relax_threshold: float,
    amorphize_threshold: float | None = None,
) -> T2Lattice:
    lattice = T2Lattice(
        size=len(initial),
        initial=_phases(initial),
        config=T2Config(
            coupling=coupling,
            crystallize_threshold=threshold,
            amorphize_threshold=(
                threshold if amorphize_threshold is None else amorphize_threshold
            ),
            memory_decay=memory_decay,
            mixed_relax_threshold=mixed_relax_threshold,
            reset_on_transition=True,
        ),
    )
    lattice.run(pulses)
    return lattice


def _locked_gates(
    *,
    memory_decay: float,
    threshold: float,
    coupling: float,
    pulse_amplitude: float,
    mixed_relax_threshold: float,
    tasks: dict[str, Any],
) -> bool:
    accumulation_task = tasks["subthreshold_accumulation"]
    accumulation = _run(
        accumulation_task["initial"],
        [pulse_amplitude] * accumulation_task["pulse_count"],
        memory_decay=memory_decay,
        threshold=threshold,
        coupling=coupling,
        mixed_relax_threshold=mixed_relax_threshold,
    )

    defect_task = tasks["defect_repair"]
    defect = _run(
        defect_task["initial"],
        defect_task["pulses"],
        memory_decay=memory_decay,
        threshold=threshold,
        coupling=coupling,
        mixed_relax_threshold=mixed_relax_threshold,
        amorphize_threshold=defect_task["amorphize_threshold"],
    )

    zero_task = tasks["zero_input_stability"]
    zero = _run(
        zero_task["initial"],
        [0.0] * zero_task["pulse_count"],
        memory_decay=memory_decay,
        threshold=threshold,
        coupling=coupling,
        mixed_relax_threshold=mixed_relax_threshold,
    )

    isolated_task = tasks["isolated_pulse_decay"]
    isolated = _run(
        isolated_task["initial"],
        [pulse_amplitude] + [0.0] * isolated_task["zero_tail"],
        memory_decay=memory_decay,
        threshold=threshold,
        coupling=coupling,
        mixed_relax_threshold=mixed_relax_threshold,
    )

    alternating_task = tasks["alternating_pulse_cancellation"]
    alternating = _run(
        alternating_task["initial"],
        [
            value
            for _ in range(alternating_task["cycles"])
            for value in (pulse_amplitude, -pulse_amplitude)
        ],
        memory_decay=memory_decay,
        threshold=threshold,
        coupling=coupling,
        mixed_relax_threshold=mixed_relax_threshold,
    )

    return all(
        [
            accumulation.phase_string() == accumulation_task["target"],
            defect.phase_string() == defect_task["target"],
            zero.phase_string() == zero_task["target"] and zero.transition_count == 0,
            isolated.phase_string() == isolated_task["target"]
            and isolated.transition_count == 0,
            alternating.phase_string() == alternating_task["target"]
            and alternating.transition_count == 0,
        ]
    )


def _flip(value: str, index: int) -> str:
    replacement = "C" if value[index] == "A" else "A"
    return value[:index] + replacement + value[index + 1 :]


def _capacity_metrics(
    *,
    size: int,
    relax_steps: int,
    memory_decay: float,
    threshold: float,
    coupling: float,
    mixed_relax_threshold: float,
) -> dict[str, Any]:
    patterns = ["".join(values) for values in itertools.product("AC", repeat=size)]

    def relax(value: str) -> tuple[str, int]:
        lattice = _run(
            value,
            [0.0] * relax_steps,
            memory_decay=memory_decay,
            threshold=threshold,
            coupling=coupling,
            mixed_relax_threshold=mixed_relax_threshold,
        )
        return lattice.phase_string(), lattice.transition_count

    stable = [pattern for pattern in patterns if relax(pattern)[0] == pattern]
    recovered = 0
    mixed = 0
    transition_cost = 0
    trials = 0
    for target in stable:
        for index in range(size):
            final_state, transitions = relax(_flip(target, index))
            trials += 1
            recovered += int(final_state == target)
            mixed += int("M" in final_state)
            transition_cost += transitions

    return {
        "stable_states": len(stable),
        "capacity_bits": round(math.log2(len(stable)), 12) if stable else 0.0,
        "one_bit_recovery_rate": round(recovered / trials, 12) if trials else 0.0,
        "mixed_dead_zone_fraction": round(mixed / trials, 12) if trials else 0.0,
        "average_relaxation_transition_cost": round(transition_cost / trials, 12)
        if trials
        else 0.0,
    }


def _majority_baseline(size: int, relax_steps: int) -> dict[str, Any]:
    patterns = ["".join(values) for values in itertools.product("AC", repeat=size)]
    stable: list[str] = []
    for pattern in patterns:
        model = MajorityCA(pattern)
        model.run(relax_steps)
        if model.state_string() == pattern:
            stable.append(pattern)

    recovered = 0
    transition_cost = 0
    trials = 0
    for target in stable:
        for index in range(size):
            model = MajorityCA(_flip(target, index))
            model.run(relax_steps)
            trials += 1
            recovered += int(model.state_string() == target)
            transition_cost += model.transitions

    return {
        "stable_states": len(stable),
        "capacity_bits": round(math.log2(len(stable)), 12),
        "one_bit_recovery_rate": round(recovered / trials, 12),
        "average_relaxation_transition_cost": round(transition_cost / trials, 12),
        "mixed_dead_zone_fraction": 0.0,
    }


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks = json.loads(ROBUSTNESS_MANIFEST.read_text(encoding="utf-8"))["locked_tasks"]
    grid = manifest["grid"]
    capacity_spec = manifest["state_capacity"]

    points: list[dict[str, Any]] = []
    for values in itertools.product(
        grid["memory_decay"],
        grid["threshold"],
        grid["coupling"],
        grid["pulse_amplitude"],
        grid["mixed_relax_threshold"],
    ):
        memory_decay, threshold, coupling, pulse_amplitude, mixed_relax_threshold = values
        all_gates = _locked_gates(
            memory_decay=memory_decay,
            threshold=threshold,
            coupling=coupling,
            pulse_amplitude=pulse_amplitude,
            mixed_relax_threshold=mixed_relax_threshold,
            tasks=tasks,
        )
        point: dict[str, Any] = {
            "memory_decay": memory_decay,
            "threshold": threshold,
            "coupling": coupling,
            "pulse_amplitude": pulse_amplitude,
            "mixed_relax_threshold": mixed_relax_threshold,
            "all_gates": all_gates,
        }
        if all_gates:
            point.update(
                _capacity_metrics(
                    size=capacity_spec["lattice_size"],
                    relax_steps=capacity_spec["relax_steps"],
                    memory_decay=memory_decay,
                    threshold=threshold,
                    coupling=coupling,
                    mixed_relax_threshold=mixed_relax_threshold,
                )
            )
        points.append(point)

    baseline = _majority_baseline(
        capacity_spec["lattice_size"], capacity_spec["relax_steps"]
    )
    passing = [point for point in points if point["all_gates"]]
    capacity_matched = [
        point
        for point in passing
        if point["capacity_bits"] >= baseline["capacity_bits"]
        and point["one_bit_recovery_rate"] >= baseline["one_bit_recovery_rate"]
    ]
    recovery_beating = [
        point
        for point in passing
        if point["one_bit_recovery_rate"] > baseline["one_bit_recovery_rate"]
    ]
    dead_zone_free = [
        point for point in passing if point["mixed_dead_zone_fraction"] == 0.0
    ]
    dominates = [
        point
        for point in passing
        if point["capacity_bits"] >= baseline["capacity_bits"]
        and point["one_bit_recovery_rate"] >= baseline["one_bit_recovery_rate"]
        and point["average_relaxation_transition_cost"]
        <= baseline["average_relaxation_transition_cost"]
    ]

    capacity_candidate = sorted(
        capacity_matched,
        key=lambda point: (
            point["mixed_dead_zone_fraction"],
            point["average_relaxation_transition_cost"],
            point["memory_decay"],
            point["threshold"],
            point["coupling"],
            point["pulse_amplitude"],
            point["mixed_relax_threshold"],
        ),
    )[0]
    recovery_candidate = sorted(
        [point for point in recovery_beating if point["capacity_bits"] > 1.0],
        key=lambda point: (
            -point["one_bit_recovery_rate"],
            -point["capacity_bits"],
            point["mixed_dead_zone_fraction"],
            point["average_relaxation_transition_cost"],
            point["memory_decay"],
            point["threshold"],
            point["coupling"],
            point["pulse_amplitude"],
            point["mixed_relax_threshold"],
        ),
    )[0]
    dead_zone_free_candidate = sorted(
        dead_zone_free,
        key=lambda point: (
            -point["one_bit_recovery_rate"],
            -point["capacity_bits"],
            point["average_relaxation_transition_cost"],
            point["memory_decay"],
            point["threshold"],
            point["coupling"],
            point["pulse_amplitude"],
            point["mixed_relax_threshold"],
        ),
    )[0]

    canonical_points = json.dumps(
        points, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    report: dict[str, Any] = {
        "baseline": baseline,
        "grid": {**grid, "points": len(points)},
        "grid_digest": hashlib.sha256(canonical_points).hexdigest(),
        "schema_version": "cosmic-organics/t2-repair-result-0.1",
        "selected_candidates": {
            "capacity_matched": capacity_candidate,
            "recovery_biased": recovery_candidate,
            "dead_zone_free": dead_zone_free_candidate,
        },
        "suite_id": manifest["suite_id"],
        "summary": {
            "all_gate_points": len(passing),
            "all_gate_fraction": round(len(passing) / len(points), 12),
            "capacity_matched_points": len(capacity_matched),
            "recovery_beating_points": len(recovery_beating),
            "dead_zone_free_points": len(dead_zone_free),
            "dominates_majority_points": len(dominates),
            "interpretation": "repair_without_dominance",
        },
    }
    canonical_report = json.dumps(
        report, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    report["result_digest"] = hashlib.sha256(canonical_report).hexdigest()
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
