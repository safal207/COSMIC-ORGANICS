"""Execute the frozen COSMIC-KERNEL-05 integrated sparse+proof workload."""
from __future__ import annotations

import hashlib
import json
from math import ceil
from pathlib import Path
import random
from time import perf_counter_ns

from benchmarks.run_bardo_proof_04 import _generic_invalid_checks
from morphos.cosmic_kernel import CommittedProofKernel
from morphos.grid2d import Grid2DConfig
from morphos.sparse_scheduler import DirtyNodeGrid2D, InstrumentedDenseGrid2D

MANIFEST = Path(__file__).with_name("cosmic_kernel_05_manifest.json")
EXECUTION_SYSTEMS = (
    "DENSE_EXECUTION",
    "DENSE_COMMITTED_PROOF",
    "SPARSE_EXECUTION",
    "SPARSE_COMMITTED_PROOF",
)
PROOF_SYSTEMS = ("DENSE_COMMITTED_PROOF", "SPARSE_COMMITTED_PROOF")
EXECUTION_METRICS = (
    "node_evaluations",
    "scheduled_work_items",
    "state_writes",
    "unchanged_evaluations_avoided",
)
PROOF_METRICS = (
    "canonical_proof_payload_bytes",
    "merkle_sibling_hashes_disclosed",
    "hash_evaluations",
    "parent_references_disclosed",
    "proof_objects_traversed",
    "audited_transitions",
)


def _grid(text: str) -> tuple[int, int]:
    left, right = text.lower().split("x", 1)
    return int(left), int(right)


def _stable_seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big")


def _config(manifest: dict, width: int, height: int) -> Grid2DConfig:
    return Grid2DConfig(width=width, height=height, **manifest["frozen_config"])


def _pulse_sequence(
    *,
    cells: int,
    activity_density: float,
    family: int,
    trial: int,
    grid_name: str,
    manifest: dict,
) -> tuple[tuple[float, ...], ...]:
    pulses: list[tuple[float, ...]] = []
    injection_ticks = set(manifest["workload"]["injection_ticks"])
    magnitude = manifest["workload"]["pulse_magnitude"]
    active_count = min(cells, max(1, ceil(cells * activity_density)))
    for logical_tick in range(1, manifest["workload"]["logical_ticks"] + 1):
        values = [0.0] * cells
        if logical_tick in injection_ticks:
            seed = _stable_seed(
                "pulse",
                family,
                trial,
                grid_name,
                f"{activity_density:.6f}",
                logical_tick,
            )
            rng = random.Random(seed)
            for site in rng.sample(range(cells), active_count):
                sign = 1.0 if _stable_seed(seed, site, "sign") % 2 == 0 else -1.0
                values[site] = sign * magnitude
        pulses.append(tuple(values))
    return tuple(pulses)


def _counter_dict(system) -> dict[str, int]:
    counters = system.scheduler_counters()
    dense_equivalent = system.tick * len(system.states)
    return {
        "node_evaluations": counters.node_evaluations,
        "scheduled_work_items": counters.scheduled_work_items,
        "state_writes": counters.state_writes,
        "unchanged_evaluations_avoided": dense_equivalent - counters.node_evaluations,
    }


def _empty_metric_totals() -> dict:
    return {metric: 0 for metric in EXECUTION_METRICS}


def build_report() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    activity_totals = {
        f"{density:.2f}": {
            name: _empty_metric_totals() for name in EXECUTION_SYSTEMS
        }
        for density in manifest["workload"]["activity_densities"]
    }
    proof_totals = {
        f"{density:.2f}": {
            name: {metric: 0 for metric in PROOF_METRICS} for name in PROOF_SYSTEMS
        }
        for density in manifest["workload"]["proof_sampling_densities"]
    }
    runtime_ns = {name: 0 for name in EXECUTION_SYSTEMS}

    state_mismatches = 0
    transition_mismatches = 0
    proof_representation_mismatches = 0
    replay_failures = 0
    valid_proof_pass = {name: 0 for name in PROOF_SYSTEMS}
    valid_proof_applicable = {name: 0 for name in PROOF_SYSTEMS}
    invalid_detected = {name: 0 for name in PROOF_SYSTEMS}
    invalid_applicable = {name: 0 for name in PROOF_SYSTEMS}
    execution_contamination_instances = 0
    max_execution_regression = 0.0
    instances = 0

    for grid_name in manifest["workload"]["grids"]:
        width, height = _grid(grid_name)
        cells = width * height
        config = _config(manifest, width, height)
        initial = "A" * cells  # exact zero-stimulus fixed point by construction.

        for activity_density in manifest["workload"]["activity_densities"]:
            activity_key = f"{activity_density:.2f}"
            for proof_density in manifest["workload"]["proof_sampling_densities"]:
                proof_key = f"{proof_density:.2f}"
                for family in manifest["workload"]["seed_families"]:
                    for trial in range(
                        manifest["workload"]["trials_per_grid_activity_proof_family"]
                    ):
                        pulses = _pulse_sequence(
                            cells=cells,
                            activity_density=activity_density,
                            family=family,
                            trial=trial,
                            grid_name=grid_name,
                            manifest=manifest,
                        )
                        proof_seed = _stable_seed(
                            "proof",
                            family,
                            trial,
                            grid_name,
                            f"{activity_density:.6f}",
                            f"{proof_density:.6f}",
                        )

                        systems = {
                            "DENSE_EXECUTION": InstrumentedDenseGrid2D(initial, config=config),
                            "DENSE_COMMITTED_PROOF": CommittedProofKernel(
                                initial,
                                config=config,
                                scheduler_cls=InstrumentedDenseGrid2D,
                                proof_density=proof_density,
                                proof_seed=proof_seed,
                            ),
                            "SPARSE_EXECUTION": DirtyNodeGrid2D(initial, config=config),
                            "SPARSE_COMMITTED_PROOF": CommittedProofKernel(
                                initial,
                                config=config,
                                scheduler_cls=DirtyNodeGrid2D,
                                proof_density=proof_density,
                                proof_seed=proof_seed,
                            ),
                        }

                        for pulse in pulses:
                            for name in EXECUTION_SYSTEMS:
                                started = perf_counter_ns()
                                systems[name].step(pulse)
                                runtime_ns[name] += perf_counter_ns() - started
                            states = [systems[name].state_string() for name in EXECUTION_SYSTEMS]
                            if len(set(states)) != 1:
                                state_mismatches += 1
                            transition_counts = [systems[name].transitions for name in EXECUTION_SYSTEMS]
                            if len(set(transition_counts)) != 1:
                                transition_mismatches += 1

                        dense_proof = systems["DENSE_COMMITTED_PROOF"]
                        sparse_proof = systems["SPARSE_COMMITTED_PROOF"]
                        if dense_proof.proof().to_jsonable() != sparse_proof.proof().to_jsonable():
                            proof_representation_mismatches += 1
                        if dense_proof.replay() != dense_proof.state_string():
                            replay_failures += 1
                        if sparse_proof.replay() != sparse_proof.state_string():
                            replay_failures += 1

                        for name in EXECUTION_SYSTEMS:
                            counters = _counter_dict(systems[name])
                            for metric, value in counters.items():
                                activity_totals[activity_key][name][metric] += value

                        raw_dense = _counter_dict(systems["DENSE_EXECUTION"])
                        obs_dense = _counter_dict(dense_proof)
                        raw_sparse = _counter_dict(systems["SPARSE_EXECUTION"])
                        obs_sparse = _counter_dict(sparse_proof)
                        contaminated = False
                        for raw, observed in ((raw_dense, obs_dense), (raw_sparse, obs_sparse)):
                            for metric in ("node_evaluations", "scheduled_work_items"):
                                base = raw[metric]
                                delta = observed[metric] - base
                                regression = 0.0 if base == 0 and delta == 0 else (
                                    float("inf") if base == 0 else max(0.0, delta / base)
                                )
                                max_execution_regression = max(max_execution_regression, regression)
                                contaminated = contaminated or delta != 0
                        execution_contamination_instances += int(contaminated)

                        for name, kernel in (
                            ("DENSE_COMMITTED_PROOF", dense_proof),
                            ("SPARSE_COMMITTED_PROOF", sparse_proof),
                        ):
                            valid_proof_applicable[name] += 1
                            valid_proof_pass[name] += int(kernel.verify_proof())
                            metrics = kernel.proof_metrics()
                            for metric in PROOF_METRICS:
                                proof_totals[proof_key][name][metric] += metrics[metric]

                            proof = kernel.proof()
                            if proof.nodes:
                                detected, applicable = _generic_invalid_checks(
                                    config, kernel.verification_context(), proof
                                )
                                invalid_detected[name] += detected
                                invalid_applicable[name] += applicable
                        instances += 1

    if instances != manifest["workload"]["total_instances"]:
        raise RuntimeError(
            f"expected {manifest['workload']['total_instances']} instances, observed {instances}"
        )

    valid_rate = {
        name: valid_proof_pass[name] / valid_proof_applicable[name]
        for name in PROOF_SYSTEMS
    }
    invalid_rate = {
        name: invalid_detected[name] / invalid_applicable[name]
        if invalid_applicable[name]
        else 0.0
        for name in PROOF_SYSTEMS
    }

    sparse_reductions = {}
    sparse_proof_reductions = {}
    for activity_key, data in activity_totals.items():
        dense = data["DENSE_EXECUTION"]["node_evaluations"]
        sparse = data["SPARSE_EXECUTION"]["node_evaluations"]
        dense_proof = data["DENSE_COMMITTED_PROOF"]["node_evaluations"]
        sparse_proof = data["SPARSE_COMMITTED_PROOF"]["node_evaluations"]
        sparse_reductions[activity_key] = 1.0 - sparse / dense
        sparse_proof_reductions[activity_key] = 1.0 - sparse_proof / dense_proof

    proof_cost_per_audited_transition = {}
    for proof_key, data in proof_totals.items():
        sparse = data["SPARSE_COMMITTED_PROOF"]
        audited = sparse["audited_transitions"]
        proof_cost_per_audited_transition[proof_key] = {
            metric: (sparse[metric] / audited if audited else None)
            for metric in PROOF_METRICS
            if metric != "audited_transitions"
        } | {"audited_transitions": audited}

    semantic_ok = (
        state_mismatches == 0
        and transition_mismatches == 0
        and proof_representation_mismatches == 0
        and replay_failures == 0
        and all(value == 1.0 for value in valid_rate.values())
        and all(value == 1.0 for value in invalid_rate.values())
    )
    sparse_required = all(
        sparse_proof_reductions[f"{density:.2f}"]
        >= manifest["decision"]["sparse_committed_proof_node_reduction_min_fraction_vs_dense_committed"]
        for density in manifest["decision"]["sparse_replication_required_in_activity_bands"]
    )
    proof_contaminates_execution = max_execution_regression > 0.02

    if not semantic_ok:
        decision = "CONTROL_FAILURE"
    elif not sparse_required:
        decision = "SPARSE_VALUE_NOT_REPLICATED"
    elif proof_contaminates_execution:
        decision = "SPARSE_VALUE_PROOF_OVERHEAD_TOO_HIGH"
    else:
        decision = "SPARSE_PLUS_PROOF_PARETO_SUPPORTED"

    return {
        "experiment_id": manifest["experiment_id"],
        "decision": decision,
        "instances": instances,
        "state_mismatches": state_mismatches,
        "transition_mismatches": transition_mismatches,
        "proof_representation_mismatches": proof_representation_mismatches,
        "replay_failures": replay_failures,
        "valid_proof_acceptance": valid_rate,
        "invalid_proof_rejection": invalid_rate,
        "invalid_proof_cases": invalid_applicable,
        "execution_contamination_instances": execution_contamination_instances,
        "max_execution_regression_from_proof": max_execution_regression,
        "sparse_node_reduction_vs_dense": sparse_reductions,
        "sparse_committed_node_reduction_vs_dense_committed": sparse_proof_reductions,
        "execution_totals_by_activity": activity_totals,
        "proof_totals_by_sampling_density": proof_totals,
        "proof_cost_per_audited_transition": proof_cost_per_audited_transition,
        "wall_runtime_ns": runtime_ns,
        "timing_decisive": False,
        "synthetic_combined_score_used": False,
    }


def main() -> None:
    print(json.dumps(build_report(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
