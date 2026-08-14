"""Map MORPHOS-T1 robustness across a declared parameter grid."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

from morphos.simulator import Phase
from morphos.temporal import TemporalConfig, TemporalLattice

DEFAULT_MANIFEST = Path(__file__).with_name("robustness_manifest.json")


def _phases(value: str) -> list[Phase]:
    return [Phase(char) for char in value]


def _run(
    initial: str,
    pulses: list[float],
    *,
    memory_decay: float,
    threshold: float,
    coupling: float,
    amorphize_threshold: float | None = None,
) -> TemporalLattice:
    lattice = TemporalLattice(
        size=len(initial),
        initial=_phases(initial),
        config=TemporalConfig(
            coupling=coupling,
            crystallize_threshold=threshold,
            amorphize_threshold=(
                threshold if amorphize_threshold is None else amorphize_threshold
            ),
            memory_decay=memory_decay,
            reset_on_transition=True,
        ),
    )
    lattice.run(pulses)
    return lattice


def evaluate_point(
    memory_decay: float,
    threshold: float,
    coupling: float,
    pulse_amplitude: float,
    tasks: dict[str, Any],
) -> dict[str, Any]:
    accumulation_task = tasks["subthreshold_accumulation"]
    accumulation = _run(
        accumulation_task["initial"],
        [pulse_amplitude] * accumulation_task["pulse_count"],
        memory_decay=memory_decay,
        threshold=threshold,
        coupling=coupling,
    )

    defect_task = tasks["defect_repair"]
    defect = _run(
        defect_task["initial"],
        defect_task["pulses"],
        memory_decay=memory_decay,
        threshold=threshold,
        coupling=coupling,
        amorphize_threshold=defect_task["amorphize_threshold"],
    )

    zero_task = tasks["zero_input_stability"]
    zero = _run(
        zero_task["initial"],
        [0.0] * zero_task["pulse_count"],
        memory_decay=memory_decay,
        threshold=threshold,
        coupling=coupling,
    )

    isolated_task = tasks["isolated_pulse_decay"]
    isolated = _run(
        isolated_task["initial"],
        [pulse_amplitude] + [0.0] * isolated_task["zero_tail"],
        memory_decay=memory_decay,
        threshold=threshold,
        coupling=coupling,
    )

    alternating_task = tasks["alternating_pulse_cancellation"]
    alternating_pulses = [
        value
        for _ in range(alternating_task["cycles"])
        for value in (pulse_amplitude, -pulse_amplitude)
    ]
    alternating = _run(
        alternating_task["initial"],
        alternating_pulses,
        memory_decay=memory_decay,
        threshold=threshold,
        coupling=coupling,
    )

    passes = {
        "alternating_pulse_cancellation": (
            alternating.phase_string() == alternating_task["target"]
            and alternating.transition_count == 0
        ),
        "defect_repair": defect.phase_string() == defect_task["target"],
        "isolated_pulse_decay": (
            isolated.phase_string() == isolated_task["target"]
            and isolated.transition_count == 0
        ),
        "subthreshold_accumulation": (
            accumulation.phase_string() == accumulation_task["target"]
        ),
        "zero_input_stability": (
            zero.phase_string() == zero_task["target"] and zero.transition_count == 0
        ),
    }

    return {
        "all_gates": all(passes.values()),
        "coupling": coupling,
        "memory_decay": memory_decay,
        "pass_mask": "".join("1" if passes[key] else "0" for key in sorted(passes)),
        "passes": passes,
        "pulse_amplitude": pulse_amplitude,
        "threshold": threshold,
    }


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    grid = manifest["grid"]
    points = [
        evaluate_point(*params, manifest["locked_tasks"])
        for params in itertools.product(
            grid["memory_decay"],
            grid["threshold"],
            grid["coupling"],
            grid["pulse_amplitude"],
        )
    ]

    stable = [point for point in points if point["all_gates"]]
    criterion_names = sorted(points[0]["passes"])
    criterion_pass_counts = {
        criterion: sum(point["passes"][criterion] for point in points)
        for criterion in criterion_names
    }

    canonical_points = json.dumps(
        points, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")

    report: dict[str, Any] = {
        "grid": {
            **grid,
            "points": len(points),
        },
        "grid_digest": hashlib.sha256(canonical_points).hexdigest(),
        "locked_tasks": manifest["locked_tasks"],
        "schema_version": "cosmic-organics/robustness-result-0.1",
        "stable_configs": [
            {
                "coupling": point["coupling"],
                "memory_decay": point["memory_decay"],
                "pulse_amplitude": point["pulse_amplitude"],
                "threshold": point["threshold"],
            }
            for point in stable
        ],
        "suite_id": manifest["suite_id"],
        "summary": {
            "criterion_pass_counts": criterion_pass_counts,
            "interpretation": "narrow_not_global",
            "stable_fraction": round(len(stable) / len(points), 12),
            "stable_points": len(stable),
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
