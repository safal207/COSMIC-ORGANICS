"""Execute the preregistered BARDO-FRONTIER-02 scheduler experiment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter_ns

from morphos.bardo_frontier import BardoFrontierGrid2D
from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.sparse_scheduler import DirtyNodeGrid2D, InstrumentedDenseGrid2D

MANIFEST = Path(__file__).with_name("bardo_frontier_02_manifest.json")
SYSTEMS = {
    "DENSE_NODE": InstrumentedDenseGrid2D,
    "DIRTY_NODE": DirtyNodeGrid2D,
    "BARDO_FRONTIER": BardoFrontierGrid2D,
}


def _grid(text: str) -> tuple[int, int]:
    width, height = text.lower().split("x", 1)
    return int(width), int(height)


def _config(protocol: dict, width: int, height: int) -> Grid2DConfig:
    frozen = protocol["frozen_config"]
    return Grid2DConfig(width=width, height=height, **frozen)


def _digest_int(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def _initial(seed: int, grid: str, trial: int, cells: int) -> str:
    # Uniform A/C endpoints are deliberate: both are zero-stimulus fixed points,
    # so scheduler measurements begin from a provably quiescent state rather than
    # from an unmeasured relaxation transient.
    phase = "A" if _digest_int(f"bardo-frontier:init:{seed}:{grid}:{trial}") % 2 == 0 else "C"
    return phase * cells


def _stable(initial: str, config: Grid2DConfig, max_ticks: int) -> tuple[str, int]:
    model = Grid2D(initial, config=config)
    for tick in range(1, max_ticks + 1):
        before = model.state_string()
        model.step(0.0)
        if model.state_string() == before:
            return model.state_string(), tick
    raise RuntimeError("preconditioning failed to reach the frozen fixed-point bound")


def _selected_sites(seed: int, grid: str, density: float, trial: int, epoch: int, cells: int) -> list[int]:
    count = cells if density == 1.0 else max(1, round(cells * density))
    scored = [
        (
            _digest_int(
                f"bardo-frontier:site:{seed}:{grid}:{density:.2f}:{trial}:{epoch}:{index}"
            ),
            index,
        )
        for index in range(cells)
    ]
    scored.sort()
    return [index for _, index in scored[:count]]


def _pulse(
    protocol: dict,
    seed: int,
    grid: str,
    density: float,
    trial: int,
    epoch: int,
    cells: int,
    initial_phase: str,
) -> list[float]:
    values = [0.0] * cells
    magnitude = float(protocol["workload"]["pulse_magnitude"])
    base_sign = 1.0 if initial_phase == "A" else -1.0
    # Alternate direction across injection epochs so the workload exercises both
    # forward and reverse A/M/C transition paths without consulting runtime state.
    sign = base_sign if epoch % 2 == 0 else -base_sign
    for index in _selected_sites(seed, grid, density, trial, epoch, cells):
        values[index] = sign * magnitude
    return values


def _empty_bucket() -> dict:
    return {
        "trials": 0,
        "node_evaluations": 0,
        "scheduled_work_items": 0,
        "unchanged_node_evaluations_avoided": 0,
        "state_writes": 0,
        "transition_records_emitted": 0,
        "relation_evaluations": 0,
        "frontier_insert_attempts": 0,
        "dedup_hits": 0,
        "runtime_ns": 0,
    }


def build_report() -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))
    workload = protocol["workload"]
    by_density = {
        f"{density:.2f}": {name: _empty_bucket() for name in SYSTEMS}
        for density in workload["activity_densities"]
    }
    state_mismatches = 0
    transition_count_mismatches = 0
    dense_negative_control_violations = 0
    precondition_failures = 0
    total_trials = 0

    for grid in workload["grids"]:
        width, height = _grid(grid)
        cells = width * height
        config = _config(protocol, width, height)
        for density in workload["activity_densities"]:
            density_key = f"{density:.2f}"
            for seed in workload["seed_families"]:
                for trial in range(workload["trials_per_grid_density_family"]):
                    initial = _initial(seed, grid, trial, cells)
                    try:
                        stable, precondition_ticks = _stable(
                            initial,
                            config,
                            workload["precondition_relaxation_max_ticks"],
                        )
                    except RuntimeError:
                        precondition_failures += 1
                        continue
                    if workload["precondition_requires_fixed_point"] and precondition_ticks > workload["precondition_relaxation_max_ticks"]:
                        precondition_failures += 1
                        continue

                    models = {
                        name: cls(stable, config=config) for name, cls in SYSTEMS.items()
                    }
                    runtime_ns = {name: 0 for name in SYSTEMS}
                    initial_phase = stable[0]
                    injections = {
                        tick: epoch
                        for epoch, tick in enumerate(workload["injection_ticks"])
                    }

                    for tick in range(1, workload["logical_ticks_per_trial"] + 1):
                        if tick in injections:
                            pulse = _pulse(
                                protocol,
                                seed,
                                grid,
                                density,
                                trial,
                                injections[tick],
                                cells,
                                initial_phase,
                            )
                        else:
                            pulse = [0.0] * cells

                        before_evals = {
                            name: model.node_evaluations for name, model in models.items()
                        }
                        order = list(SYSTEMS)
                        shift = (total_trials + tick) % len(order)
                        order = order[shift:] + order[:shift]
                        for name in order:
                            started = perf_counter_ns()
                            models[name].step(pulse)
                            runtime_ns[name] += perf_counter_ns() - started

                        dense = models["DENSE_NODE"]
                        dirty = models["DIRTY_NODE"]
                        bardo = models["BARDO_FRONTIER"]
                        if not (
                            dense.state_string()
                            == dirty.state_string()
                            == bardo.state_string()
                        ):
                            state_mismatches += 1
                        if not (dense.transitions == dirty.transitions == bardo.transitions):
                            transition_count_mismatches += 1

                        if density == protocol["acceptance"]["dense_negative_control_density"] and tick in injections:
                            dirty_delta = dirty.node_evaluations - before_evals["DIRTY_NODE"]
                            bardo_delta = bardo.node_evaluations - before_evals["BARDO_FRONTIER"]
                            if dirty_delta != cells or bardo_delta != cells:
                                dense_negative_control_violations += 1

                    for name, model in models.items():
                        bucket = by_density[density_key][name]
                        bucket["trials"] += 1
                        bucket["node_evaluations"] += model.node_evaluations
                        bucket["scheduled_work_items"] += model.scheduled_work_items
                        bucket["unchanged_node_evaluations_avoided"] += model.unchanged_node_evaluations_avoided
                        bucket["state_writes"] += model.state_writes
                        bucket["transition_records_emitted"] += model.transition_records_emitted
                        bucket["frontier_insert_attempts"] += model.frontier_insert_attempts
                        bucket["dedup_hits"] += model.dedup_hits
                        bucket["runtime_ns"] += runtime_ns[name]
                        bucket["relation_evaluations"] += getattr(model, "relation_evaluations", 0)
                    total_trials += 1

    expected_trials = workload["total_trials"]
    primary_metrics_complete = total_trials == expected_trials and all(
        all(
            isinstance(bucket[metric], int)
            for metric in protocol["primary_metrics"]
        )
        for systems in by_density.values()
        for bucket in systems.values()
    )

    density_comparison = {}
    sparse_generic_bands = 0
    bardo_supported_bands = 0
    bardo_sparse_regressions = 0
    for density in workload["activity_densities"]:
        key = f"{density:.2f}"
        dense = by_density[key]["DENSE_NODE"]
        dirty = by_density[key]["DIRTY_NODE"]
        bardo = by_density[key]["BARDO_FRONTIER"]
        dirty_reduction = 1.0 - dirty["node_evaluations"] / dense["node_evaluations"]
        bardo_vs_dirty_reduction = 1.0 - bardo["node_evaluations"] / max(1, dirty["node_evaluations"])
        density_comparison[key] = {
            "dirty_node_evaluation_reduction_vs_dense": dirty_reduction,
            "bardo_node_evaluation_reduction_vs_dirty": bardo_vs_dirty_reduction,
            "bardo_node_evaluation_fraction_vs_dirty": bardo["node_evaluations"] / max(1, dirty["node_evaluations"]),
            "dirty_runtime_fraction_vs_dense": dirty["runtime_ns"] / max(1, dense["runtime_ns"]),
            "bardo_runtime_fraction_vs_dirty": bardo["runtime_ns"] / max(1, dirty["runtime_ns"]),
        }
        if density in protocol["acceptance"]["sparse_density_bands"]:
            if dirty_reduction >= protocol["acceptance"]["generic_sparse_node_evaluation_reduction_min_fraction_sparse_band"]:
                sparse_generic_bands += 1
            if bardo_vs_dirty_reduction >= protocol["acceptance"]["bardo_specific_node_evaluation_reduction_min_fraction_vs_dirty"]:
                bardo_supported_bands += 1
            if bardo["node_evaluations"] > dirty["node_evaluations"]:
                bardo_sparse_regressions += 1

    controls_ok = (
        precondition_failures == 0
        and state_mismatches <= protocol["acceptance"]["maximum_state_mismatches"]
        and transition_count_mismatches <= protocol["acceptance"]["maximum_transition_count_mismatches"]
        and dense_negative_control_violations == 0
    )
    generic_sparse_supported = controls_ok and sparse_generic_bands == len(
        protocol["acceptance"]["sparse_density_bands"]
    )
    bardo_specific_supported = (
        generic_sparse_supported
        and bardo_sparse_regressions == 0
        and bardo_supported_bands
        >= protocol["acceptance"]["bardo_specific_required_sparse_density_bands"]
    )

    if not controls_ok:
        decision = "CONTROL_FAILURE"
    elif not primary_metrics_complete:
        decision = "INCOMPLETE_REQUIRED_METRICS"
    elif not generic_sparse_supported:
        decision = "NO_SPARSE_EXECUTION_VALUE"
    elif bardo_specific_supported:
        decision = "BARDO_FRONTIER_VALUE_SUPPORTED"
    else:
        decision = "SPARSE_EXECUTION_VALUE_ONLY"

    return {
        "experiment_id": protocol["experiment_id"],
        "frozen_control_head": "de23537427302cc24c25ad41eacb71496cb6c124",
        "candidate_results_observed_after_preregistration": True,
        "total_trials": total_trials,
        "precondition_failures": precondition_failures,
        "state_mismatches": state_mismatches,
        "transition_count_mismatches": transition_count_mismatches,
        "dense_negative_control_violations": dense_negative_control_violations,
        "primary_metrics_complete": primary_metrics_complete,
        "by_density": by_density,
        "density_comparison": density_comparison,
        "generic_sparse_supported": generic_sparse_supported,
        "bardo_specific_supported": bardo_specific_supported,
        "bardo_supported_sparse_bands": bardo_supported_bands,
        "bardo_sparse_regressions": bardo_sparse_regressions,
        "decision": decision,
        "timing_decides_bardo_claim": False,
        "claim_boundary": protocol["claim_boundary"],
    }


def main() -> None:
    result = build_report()
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["decision"] == "CONTROL_FAILURE":
        raise SystemExit("BARDO-FRONTIER-02 control failure")


if __name__ == "__main__":
    main()
