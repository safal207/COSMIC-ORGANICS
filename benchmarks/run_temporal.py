"""Run the MORPHOS-T1 temporal-memory falsification suite."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from morphos.simulator import Lattice, Phase, SimulationConfig
from morphos.temporal import TemporalConfig, TemporalLattice


DEFAULT_MANIFEST = Path(__file__).with_name("temporal_manifest.json")


def _phases(value: str) -> list[Phase]:
    return [Phase(char) for char in value]


def _accuracy(actual: list[Phase], target: list[Phase]) -> float:
    return sum(a == b for a, b in zip(actual, target)) / len(target)


def _temporal_metrics(lattice: TemporalLattice, target: list[Phase]) -> dict[str, Any]:
    return {
        "accuracy": round(_accuracy([cell.phase for cell in lattice.cells], target), 12),
        "final_state": lattice.phase_string(),
        "max_abs_activation": round(lattice.max_abs_activation_seen, 12),
        "transition_count": lattice.transition_count,
    }


def _baseline_metrics(lattice: Lattice, target: list[Phase]) -> dict[str, Any]:
    return {
        "accuracy": round(_accuracy([cell.phase for cell in lattice.cells], target), 12),
        "final_state": lattice.phase_string(),
        "transition_count": lattice.transition_count,
    }


def run_benchmark(item: dict[str, Any]) -> dict[str, Any]:
    config = TemporalConfig(**item["config"])
    initial = _phases(item["initial"])
    target = _phases(item["target"])

    temporal = TemporalLattice(size=len(initial), initial=initial, config=config)
    temporal.run(item["pulses"])

    baseline = Lattice(
        size=len(initial),
        initial=initial,
        config=SimulationConfig(
            coupling=config.coupling,
            crystallize_threshold=config.crystallize_threshold,
            amorphize_threshold=config.amorphize_threshold,
        ),
    )
    baseline.run(item["pulses"])

    temporal_metrics = _temporal_metrics(temporal, target)
    baseline_metrics = _baseline_metrics(baseline, target)
    temporal_accuracy = temporal_metrics["accuracy"]
    baseline_accuracy = baseline_metrics["accuracy"]

    criterion = item["criterion"]
    if criterion == "temporal_accuracy_gt_memoryless":
        criterion_passed = temporal_accuracy > baseline_accuracy
    elif criterion == "temporal_accuracy_eq_1_no_transitions":
        criterion_passed = (
            temporal_accuracy == 1.0 and temporal_metrics["transition_count"] == 0
        )
    else:
        raise ValueError(f"unknown criterion: {criterion}")

    return {
        "accuracy_delta": round(temporal_accuracy - baseline_accuracy, 12),
        "baseline": baseline_metrics,
        "claim": item["claim"],
        "criterion": criterion,
        "criterion_passed": criterion_passed,
        "id": item["id"],
        "temporal": temporal_metrics,
    }


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = [run_benchmark(item) for item in manifest["benchmarks"]]
    locked = next(
        result for result in results if result["id"] == "subthreshold-accumulation-locked"
    )
    controls = [
        result for result in results if result["id"] != "subthreshold-accumulation-locked"
    ]

    report: dict[str, Any] = {
        "baseline_id": manifest["baseline"]["id"],
        "results": results,
        "schema_version": "cosmic-organics/benchmark-result-0.1",
        "suite_id": manifest["suite_id"],
        "summary": {
            "benchmarks": len(results),
            "criteria_passed": sum(result["criterion_passed"] for result in results),
            "locked_failure_repaired": locked["criterion_passed"],
            "negative_controls_passed": all(
                result["criterion_passed"] for result in controls
            ),
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
