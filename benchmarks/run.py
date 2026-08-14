"""Run the deterministic P1 MORPHOS falsification benchmarks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from morphos.simulator import Lattice, Phase, SimulationConfig


DEFAULT_MANIFEST = Path(__file__).with_name("manifest.json")


def _phases(value: str) -> list[Phase]:
    return [Phase(char) for char in value]


def _accuracy(actual: list[Phase], target: list[Phase]) -> float:
    if len(actual) != len(target):
        raise ValueError("actual and target lengths differ")
    return sum(a == b for a, b in zip(actual, target)) / len(target)


def _metrics(lattice: Lattice, target: list[Phase]) -> dict[str, Any]:
    accuracy = _accuracy([cell.phase for cell in lattice.cells], target)
    return {
        "accuracy": round(accuracy, 12),
        "final_state": lattice.phase_string(),
        "order_parameter": round(lattice.order_parameter, 12),
        "transition_count": lattice.transition_count,
    }


def _criterion_passed(criterion: str, morphos_accuracy: float, baseline_accuracy: float) -> bool:
    if criterion == "morphos_accuracy_gt_baseline":
        return morphos_accuracy > baseline_accuracy
    if criterion == "morphos_accuracy_eq_1":
        return morphos_accuracy == 1.0
    raise ValueError(f"unknown criterion: {criterion}")


def run_benchmark(item: dict[str, Any]) -> dict[str, Any]:
    config = SimulationConfig(**item["config"])
    initial = _phases(item["initial"])
    target = _phases(item["target"])

    morphos = Lattice(size=len(initial), initial=initial, config=config)
    morphos.run(item["pulses"])

    baseline_config = SimulationConfig(
        coupling=0.0,
        crystallize_threshold=config.crystallize_threshold,
        amorphize_threshold=config.amorphize_threshold,
    )
    baseline = Lattice(size=len(initial), initial=initial, config=baseline_config)
    baseline.run(item["pulses"])

    morphos_metrics = _metrics(morphos, target)
    baseline_metrics = _metrics(baseline, target)
    delta = morphos_metrics["accuracy"] - baseline_metrics["accuracy"]

    return {
        "accuracy_delta": round(delta, 12),
        "baseline": baseline_metrics,
        "claim": item["claim"],
        "criterion": item["criterion"],
        "criterion_passed": _criterion_passed(
            item["criterion"],
            morphos_metrics["accuracy"],
            baseline_metrics["accuracy"],
        ),
        "id": item["id"],
        "morphos": morphos_metrics,
    }


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = [run_benchmark(item) for item in manifest["benchmarks"]]

    report: dict[str, Any] = {
        "baseline_id": manifest["baseline"]["id"],
        "results": results,
        "schema_version": "cosmic-organics/benchmark-result-0.1",
        "suite_id": manifest["suite_id"],
        "summary": {
            "benchmarks": len(results),
            "criteria_passed": sum(result["criterion_passed"] for result in results),
            "distinct_baseline_advantage_observed": any(
                result["accuracy_delta"] > 0 for result in results
            ),
            "known_failure_cases": [
                result["id"] for result in results if not result["criterion_passed"]
            ],
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

    report = run_suite(args.manifest)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
