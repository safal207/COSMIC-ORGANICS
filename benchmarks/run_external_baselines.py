"""Compare MORPHOS locked toy tasks with simple external algorithmic baselines."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.external_baselines import LeakyThreeState, MajorityCA
from morphos.simulator import Lattice, Phase, SimulationConfig
from morphos.temporal import TemporalConfig, TemporalLattice

DEFAULT_MANIFEST = Path(__file__).with_name("external_baseline_manifest.json")


def _phases(value: str) -> list[Phase]:
    return [Phase(char) for char in value]


def _accuracy(actual: str, target: str) -> float:
    return round(sum(a == b for a, b in zip(actual, target)) / len(target), 12)


def _run_morphos(task: dict[str, Any]) -> tuple[str, int]:
    spec = task["morphos"]
    kind = spec["kind"]
    if kind == "morphos0":
        lattice = Lattice(
            size=len(task["initial"]),
            initial=_phases(task["initial"]),
            config=SimulationConfig(**spec["config"]),
        )
    elif kind == "morphos_t1":
        lattice = TemporalLattice(
            size=len(task["initial"]),
            initial=_phases(task["initial"]),
            config=TemporalConfig(**spec["config"]),
        )
    else:
        raise ValueError(f"unknown MORPHOS kind: {kind}")
    lattice.run(task["pulses"])
    return lattice.phase_string(), lattice.transition_count


def _run_baseline(task: dict[str, Any]) -> tuple[str, int]:
    spec = task["baseline"]
    kind = spec["kind"]
    if kind == "majority_ca":
        model = MajorityCA(task["initial"])
        model.run(spec["steps"])
        return model.state_string(), model.transitions
    if kind == "leaky_three_state":
        model = LeakyThreeState(
            len(task["initial"]),
            memory_decay=spec["memory_decay"],
            threshold=spec["threshold"],
        )
        model.run(task["pulses"])
        return model.state_string(), model.transitions
    raise ValueError(f"unknown baseline kind: {kind}")


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    morphos_state, morphos_transitions = _run_morphos(task)
    baseline_state, baseline_transitions = _run_baseline(task)
    morphos_accuracy = _accuracy(morphos_state, task["target"])
    baseline_accuracy = _accuracy(baseline_state, task["target"])
    if morphos_accuracy > baseline_accuracy:
        outcome = "morphos_win"
    elif baseline_accuracy > morphos_accuracy:
        outcome = "baseline_win"
    else:
        outcome = "tie"

    return {
        "baseline": {
            "accuracy": baseline_accuracy,
            "final_state": baseline_state,
            "kind": task["baseline"]["kind"],
            "transition_count": baseline_transitions,
        },
        "claim": task["claim"],
        "id": task["id"],
        "morphos": {
            "accuracy": morphos_accuracy,
            "final_state": morphos_state,
            "kind": task["morphos"]["kind"],
            "transition_count": morphos_transitions,
        },
        "outcome": outcome,
        "target": task["target"],
    }


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = [run_task(task) for task in manifest["tasks"]]
    summary = {
        "baseline_wins": sum(result["outcome"] == "baseline_win" for result in results),
        "distinct_advantage_observed": any(
            result["outcome"] == "morphos_win" for result in results
        ),
        "morphos_wins": sum(result["outcome"] == "morphos_win" for result in results),
        "ties": sum(result["outcome"] == "tie" for result in results),
    }
    report: dict[str, Any] = {
        "results": results,
        "schema_version": "cosmic-organics/external-baseline-result-0.1",
        "suite_id": manifest["suite_id"],
        "summary": summary,
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
