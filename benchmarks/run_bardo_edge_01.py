"""Execute frozen BARDO-EDGE-01 over held-out MORPHOS-W8.5 corpora."""
from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.bardo_edges import BardoEdgeFieldObserverGrid2D
from morphos.transition_edges import ConventionalEdgeObserverGrid2D
from morphos.witness import WitnessLaw
from morphos.witness_multierasure import MultiErasureAuthorityGrid2D

MANIFEST = Path(__file__).with_name("bardo_edge_01_manifest.json")
SYSTEMS = {
    "NODE_ONLY": MultiErasureAuthorityGrid2D,
    "CONVENTIONAL_EDGE": ConventionalEdgeObserverGrid2D,
    "BARDO_EDGE": BardoEdgeFieldObserverGrid2D,
}


def _grid_size(text: str) -> tuple[int, int]:
    left, right = text.lower().split("x", 1)
    return int(left), int(right)


def _node_transition_scan(snapshots: tuple[str, ...]) -> tuple[tuple[int, int, str, str], ...]:
    """Reconstruct local transition occurrences from full node snapshots."""
    reconstructed: list[tuple[int, int, str, str]] = []
    for tick, (before, after) in enumerate(zip(snapshots, snapshots[1:]), start=1):
        if len(before) != len(after):
            raise ValueError("snapshot width changed during reconstruction")
        for site, (from_phase, to_phase) in enumerate(zip(before, after)):
            if from_phase != to_phase:
                reconstructed.append((tick, site, from_phase, to_phase))
    return tuple(reconstructed)


def _relation_count(model) -> int | None:
    if isinstance(model, ConventionalEdgeObserverGrid2D):
        return len(model._records_by_relation)
    if isinstance(model, BardoEdgeFieldObserverGrid2D):
        return len(model.edge_field)
    return None


def _trial(cls, target, source, config, hierarchy, mirror_law, protocol) -> dict:
    model = cls(
        target,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(
            witness_drive=protocol["workload"]["witness_drive"],
            commit_delay=protocol["workload"]["witness_commit_delay"],
        ),
    )
    _corrupt_all(model, source)
    replay_initial = model.state_string()
    snapshots = [replay_initial]
    phase_change_checks = 0
    state_at_8 = None

    # Runtime timing contains the real model path plus the exact same state-delta
    # accounting/snapshot retention for every system. Observer index inspection,
    # replay and audit reconstruction are measured separately after this timer.
    started = perf_counter_ns()
    for tick in range(1, protocol["workload"]["retention_tick"] + 1):
        before = model.state_string()
        transitions_before = model.transitions
        model.step(0.0)
        after = model.state_string()
        actual_changes = sum(a != b for a, b in zip(before, after))
        counted_changes = model.transitions - transitions_before
        if actual_changes != counted_changes:
            raise RuntimeError("MORPHOS transition counter diverged from state delta")
        phase_change_checks += actual_changes
        snapshots.append(after)
        if tick == protocol["workload"]["evaluation_tick"]:
            state_at_8 = after
    elapsed_ns = perf_counter_ns() - started

    final_state = model.state_string()
    frozen_snapshots = tuple(snapshots)

    node_reconstruction_started = perf_counter_ns()
    node_reconstructed = _node_transition_scan(frozen_snapshots)
    node_reconstruction_ns = perf_counter_ns() - node_reconstruction_started
    if len(node_reconstructed) != phase_change_checks:
        raise RuntimeError("node reconstruction missed or invented a transition")

    result = {
        "state_at_8": state_at_8,
        "state_at_12": final_state,
        "exact_at_8": state_at_8 == target,
        "exact_at_12": final_state == target,
        "elapsed_ns": elapsed_ns,
        "phase_changes": phase_change_checks,
        "node_reconstruction_observations": (
            len(target) * protocol["workload"]["retention_tick"]
        ),
        "node_reconstruction_ns": node_reconstruction_ns,
        "node_reconstruction_ambiguities": 0,
        "multi_erasure_decode_events": model.multi_erasure_decode_events,
        "protected_targets": tuple(sorted(model.protected_targets.items())),
    }

    if hasattr(model, "transition_records"):
        records = tuple(model.transition_records)
        if len(records) != phase_change_checks:
            raise RuntimeError("edge observer missed or invented a transition")

        replay_started = perf_counter_ns()
        replayed = model.replay(replay_initial)
        replay_ns = perf_counter_ns() - replay_started

        trajectory_started = perf_counter_ns()
        audit_trajectory = tuple(
            (record.logical_tick, record.site, record.from_phase, record.to_phase)
            for record in records
        )
        trajectory_reconstruction_ns = perf_counter_ns() - trajectory_started

        if audit_trajectory != node_reconstructed:
            raise RuntimeError("edge trajectory does not match node-observed trajectory")

        relation_count = _relation_count(model)
        if relation_count is None:
            raise RuntimeError("edge representation relation count unavailable")

        result.update(
            {
                "transition_records": records,
                "record_count": len(records),
                "record_ids": tuple(record.transition_id for record in records),
                "metadata_bytes": model.transition_metadata_bytes(),
                "replay_exact": replayed == final_state,
                "replay_ns": replay_ns,
                "trajectory_reconstruction_ns": trajectory_reconstruction_ns,
                "phase_change_coverage": (
                    len(records) / phase_change_checks if phase_change_checks else 1.0
                ),
                "phantom_transitions": max(0, len(records) - phase_change_checks),
                "missing_transitions": max(0, phase_change_checks - len(records)),
                "source_destination_relation_coverage": (
                    sum(
                        record.source_site is not None
                        and record.destination_site is not None
                        for record in records
                    )
                    / len(records)
                    if records
                    else 1.0
                ),
                "edge_reconstruction_work": len(records),
                "peak_transition_objects": len(records) + relation_count,
                "edge_writes": len(records),
                "edge_reads_during_replay": len(records),
                "ambiguous_transition_reconstructions": 0,
            }
        )
    else:
        result.update(
            {
                "transition_records": (),
                "record_count": 0,
                "record_ids": (),
                "metadata_bytes": 0,
                "replay_exact": None,
                "replay_ns": None,
                "trajectory_reconstruction_ns": node_reconstruction_ns,
                "phase_change_coverage": None,
                "phantom_transitions": None,
                "missing_transitions": None,
                "source_destination_relation_coverage": None,
                "edge_reconstruction_work": None,
                "peak_transition_objects": None,
                "edge_writes": None,
                "edge_reads_during_replay": None,
                "ambiguous_transition_reconstructions": 0,
            }
        )
    return result


def build_report(speed_rounds: int = 3) -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    per_system = {
        name: {
            "exact8": 0,
            "exact12": 0,
            "previous_success_regressions": 0,
            "phase_changes": 0,
            "records": 0,
            "metadata_bytes": 0,
            "node_work": [],
            "edge_work": [],
            "peak_objects": [],
            "edge_writes": 0,
            "edge_reads": 0,
            "ambiguous": 0,
            "runtime_round_ns": [0] * speed_rounds,
            "replay_round_ns": [0] * speed_rounds,
            "trajectory_round_ns": [0] * speed_rounds,
            "replay_pass": 0,
            "coverage": [],
            "relation_coverage": [],
            "phantom": 0,
            "missing": 0,
            "identity_stable": 0,
        }
        for name in SYSTEMS
    }
    trials = 0
    semantic_mismatches = 0
    outcome_mismatches = 0
    authority_mismatches = 0
    identity_instability = {"CONVENTIONAL_EDGE": 0, "BARDO_EDGE": 0}

    for corpus in protocol["workload"]["corpora"]:
        width, height = _grid_size(corpus["grid"])
        cells = width * height
        config, hierarchy = _s2_components(base, width, height)
        mirror_law = _m2_law(base)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(
                corpus["seed"], protocol["workload"]["samples_per_corpus"], cells
            ),
            config,
            hierarchy,
            protocol["workload"]["target_discovery_steps"],
        )[: protocol["workload"]["max_targets"]]
        if len(targets) != protocol["workload"]["max_targets"]:
            raise RuntimeError("held-out corpus did not produce the frozen target count")

        for target_index, target in enumerate(targets):
            sources = _noise_indices(
                corpus["seed"],
                target_index,
                cells,
                protocol["workload"]["trials_per_target"],
            )
            for source in sources:
                reference_round = None
                reference_ids: dict[str, tuple[str, ...]] = {}
                for round_index in range(speed_rounds):
                    names = list(SYSTEMS)
                    shift = (trials + round_index) % len(names)
                    order = names[shift:] + names[:shift]
                    round_results = {}
                    for name in order:
                        result = _trial(
                            SYSTEMS[name],
                            target,
                            source,
                            config,
                            hierarchy,
                            mirror_law,
                            protocol,
                        )
                        per_system[name]["runtime_round_ns"][round_index] += result[
                            "elapsed_ns"
                        ]
                        per_system[name]["trajectory_round_ns"][round_index] += result[
                            "trajectory_reconstruction_ns"
                        ]
                        if result["replay_ns"] is not None:
                            per_system[name]["replay_round_ns"][round_index] += result[
                                "replay_ns"
                            ]
                        round_results[name] = result

                        if result["record_ids"]:
                            if name not in reference_ids:
                                reference_ids[name] = result["record_ids"]
                            elif result["record_ids"] != reference_ids[name]:
                                identity_instability[name] += 1

                    node = round_results["NODE_ONLY"]
                    conventional = round_results["CONVENTIONAL_EDGE"]
                    bardo = round_results["BARDO_EDGE"]
                    if not (
                        node["state_at_8"]
                        == conventional["state_at_8"]
                        == bardo["state_at_8"]
                        and node["state_at_12"]
                        == conventional["state_at_12"]
                        == bardo["state_at_12"]
                    ):
                        outcome_mismatches += 1
                    if not (
                        node["protected_targets"]
                        == conventional["protected_targets"]
                        == bardo["protected_targets"]
                        and node["multi_erasure_decode_events"]
                        == conventional["multi_erasure_decode_events"]
                        == bardo["multi_erasure_decode_events"]
                    ):
                        authority_mismatches += 1
                    if conventional["transition_records"] != bardo["transition_records"]:
                        semantic_mismatches += 1
                    if round_index == 0:
                        reference_round = round_results

                assert reference_round is not None
                node_reference = reference_round["NODE_ONLY"]
                for name, result in reference_round.items():
                    bucket = per_system[name]
                    bucket["exact8"] += int(result["exact_at_8"])
                    bucket["exact12"] += int(result["exact_at_12"])
                    bucket["previous_success_regressions"] += int(
                        node_reference["exact_at_8"] and not result["exact_at_8"]
                    )
                    bucket["phase_changes"] += result["phase_changes"]
                    bucket["node_work"].append(result["node_reconstruction_observations"])
                    bucket["ambiguous"] += result["ambiguous_transition_reconstructions"]
                    if result["edge_reconstruction_work"] is not None:
                        bucket["records"] += result["record_count"]
                        bucket["metadata_bytes"] += result["metadata_bytes"]
                        bucket["edge_work"].append(result["edge_reconstruction_work"])
                        bucket["peak_objects"].append(result["peak_transition_objects"])
                        bucket["edge_writes"] += result["edge_writes"]
                        bucket["edge_reads"] += result["edge_reads_during_replay"]
                        bucket["replay_pass"] += int(result["replay_exact"])
                        bucket["coverage"].append(result["phase_change_coverage"])
                        bucket["relation_coverage"].append(
                            result["source_destination_relation_coverage"]
                        )
                        bucket["phantom"] += result["phantom_transitions"]
                        bucket["missing"] += result["missing_transitions"]
                trials += 1

    if trials != protocol["workload"]["total_trials"]:
        raise RuntimeError(f"expected 864 held-out trials, observed {trials}")

    summary = {}
    for name, bucket in per_system.items():
        edge_present = bool(bucket["edge_work"])
        summary[name] = {
            "trials": trials,
            "exact_recovery_at_8": bucket["exact8"] / trials,
            "exact_recovery_at_12": bucket["exact12"] / trials,
            "previous_success_regressions": bucket["previous_success_regressions"],
            "phase_changes": bucket["phase_changes"],
            "transition_records": bucket["records"],
            "transition_metadata_bytes": bucket["metadata_bytes"],
            "median_node_reconstruction_observations": median(bucket["node_work"]),
            "median_edge_reconstruction_work": median(bucket["edge_work"]) if edge_present else None,
            "median_peak_transition_objects": median(bucket["peak_objects"]) if edge_present else None,
            "edge_writes": bucket["edge_writes"] if edge_present else None,
            "edge_reads_during_replay": bucket["edge_reads"] if edge_present else None,
            "ambiguous_transition_reconstructions": bucket["ambiguous"],
            "replay_correctness": bucket["replay_pass"] / trials if edge_present else None,
            "minimum_phase_change_coverage": min(bucket["coverage"]) if edge_present else None,
            "source_destination_relation_coverage": (
                sum(bucket["relation_coverage"]) / len(bucket["relation_coverage"])
                if edge_present
                else None
            ),
            "transition_identity_stability": (
                1.0 - identity_instability[name] / max(1, trials * (speed_rounds - 1))
                if edge_present
                else None
            ),
            "phantom_transitions": bucket["phantom"] if edge_present else None,
            "missing_transitions": bucket["missing"] if edge_present else None,
            "runtime_round_ns": bucket["runtime_round_ns"],
            "median_runtime_round_ns": median(bucket["runtime_round_ns"]),
            "replay_round_ns": bucket["replay_round_ns"] if edge_present else None,
            "median_replay_round_ns": median(bucket["replay_round_ns"]) if edge_present else None,
            "trajectory_reconstruction_round_ns": bucket["trajectory_round_ns"],
            "median_trajectory_reconstruction_round_ns": median(bucket["trajectory_round_ns"]),
            "additional_allocations": None,
            "additional_allocations_note": (
                "Not used as a decision route in v0.1: preregistration qualified this metric "
                "as 'where measurable', and no allocation profiler is introduced after candidate observation."
            ),
        }

    conventional = summary["CONVENTIONAL_EDGE"]
    bardo = summary["BARDO_EDGE"]
    conventional_work_reduction = 1.0 - (
        conventional["median_edge_reconstruction_work"]
        / conventional["median_node_reconstruction_observations"]
    )
    bardo_work_reduction = 1.0 - (
        bardo["median_edge_reconstruction_work"]
        / bardo["median_node_reconstruction_observations"]
    )

    controls_ok = (
        outcome_mismatches == 0
        and authority_mismatches == 0
        and conventional["previous_success_regressions"] == 0
        and conventional["replay_correctness"] == 1.0
        and conventional["minimum_phase_change_coverage"] == 1.0
        and conventional["transition_identity_stability"] == 1.0
        and conventional["phantom_transitions"] == 0
        and conventional["missing_transitions"] == 0
    )
    explicit_edge_supported = controls_ok and (
        conventional_work_reduction
        >= protocol["acceptance"]["explicit_edge_reconstruction_work_reduction_min_fraction"]
        or conventional["ambiguous_transition_reconstructions"]
        < summary["NODE_ONLY"]["ambiguous_transition_reconstructions"]
    )

    bardo_semantics_ok = (
        controls_ok
        and semantic_mismatches == 0
        and bardo["previous_success_regressions"] == 0
        and bardo["replay_correctness"] == 1.0
        and bardo["minimum_phase_change_coverage"] == 1.0
        and bardo["transition_identity_stability"] == 1.0
        and bardo["phantom_transitions"] == 0
        and bardo["missing_transitions"] == 0
        and bardo["source_destination_relation_coverage"]
        == conventional["source_destination_relation_coverage"]
    )

    candidate_metrics = {
        "metadata_fraction_vs_conventional": bardo["transition_metadata_bytes"] / max(1, conventional["transition_metadata_bytes"]),
        "reconstruction_work_fraction_vs_conventional": bardo["median_edge_reconstruction_work"] / max(1, conventional["median_edge_reconstruction_work"]),
        "peak_transition_objects_fraction_vs_conventional": bardo["median_peak_transition_objects"] / max(1, conventional["median_peak_transition_objects"]),
        "edge_writes_fraction_vs_conventional": bardo["edge_writes"] / max(1, conventional["edge_writes"]),
        "edge_reads_replay_fraction_vs_conventional": bardo["edge_reads_during_replay"] / max(1, conventional["edge_reads_during_replay"]),
        "runtime_fraction_vs_conventional": bardo["median_runtime_round_ns"] / max(1, conventional["median_runtime_round_ns"]),
        "replay_time_fraction_vs_conventional": bardo["median_replay_round_ns"] / max(1, conventional["median_replay_round_ns"]),
        "trajectory_reconstruction_time_fraction_vs_conventional": (
            bardo["median_trajectory_reconstruction_round_ns"]
            / max(1, conventional["median_trajectory_reconstruction_round_ns"])
        ),
    }
    required_metric_names = tuple(candidate_metrics)
    required_metrics_complete = all(
        isinstance(candidate_metrics[name], (int, float)) for name in required_metric_names
    )

    threshold = 1.0 - protocol["acceptance"]["bardo_specific_improvement_min_fraction"]
    bardo_specific_supported = (
        bardo_semantics_ok
        and required_metrics_complete
        and any(fraction <= threshold for fraction in candidate_metrics.values())
    )

    if not controls_ok:
        decision = "REJECTED_CONTROL_FAILURE"
    elif not explicit_edge_supported:
        decision = "NO_MEASURED_EDGE_REPRESENTATION_VALUE"
    elif bardo_specific_supported:
        decision = "BARDO_SPECIFIC_VALUE_SUPPORTED"
    elif not required_metrics_complete:
        decision = "INCOMPLETE_PREREG_METRICS"
    else:
        decision = "EXPLICIT_EDGE_VALUE_ONLY_NO_BARDO_SPECIFIC_ADVANTAGE"

    return {
        "experiment_id": protocol["experiment_id"],
        "control_head": "082ad50e8c1870addc8aef41c7abc831704ea151",
        "candidate_results_observed_after_preregistration": True,
        "speed_rounds": speed_rounds,
        "summary": summary,
        "cross_system": {
            "outcome_mismatches": outcome_mismatches,
            "authority_mismatches": authority_mismatches,
            "semantic_mismatches_conventional_vs_bardo": semantic_mismatches,
            "conventional_reconstruction_work_reduction": conventional_work_reduction,
            "bardo_reconstruction_work_reduction": bardo_work_reduction,
            **candidate_metrics,
        },
        "decision_metric_coverage": {
            "required_metrics": list(required_metric_names),
            "required_metrics_complete": required_metrics_complete,
            "additional_allocations": "optional_where_measurable_not_decisive_v0.1",
        },
        "explicit_edge_supported": explicit_edge_supported,
        "bardo_specific_supported": bardo_specific_supported,
        "decision": decision,
        "claim_boundary": (
            "Classical deterministic software/lattice evidence only. Runtime, replay and "
            "trajectory timing are Python-runner measurements, not hardware or physical-energy evidence."
        ),
    }


def main() -> None:
    report = build_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["decision"] in {"REJECTED_CONTROL_FAILURE", "INCOMPLETE_PREREG_METRICS"}:
        raise SystemExit(f"BARDO-EDGE-01 non-promotable decision: {report['decision']}")


if __name__ == "__main__":
    main()
