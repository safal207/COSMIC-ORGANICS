"""Fresh held-out construct-validity challenge for BARDO-PROOF-04."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from benchmarks.run_bardo_proof_03 import COST_METRICS, _instance
from morphos.bardo_proof_edges import BardoProof, bardo_proof_metrics, verify_bardo_proof
from morphos.dag_parent_commit import (
    DagParentCommitProof,
    build_dag_nodes,
    dag_parent_commit_metrics,
    verify_dag_parent_commit,
)
from morphos.proof_controls_v02 import CausalDagProof, proof_metrics, verify_causal_dag

MANIFEST = Path(__file__).with_name("bardo_proof_04_manifest.json")
SYSTEMS = (
    "EXPLICIT_CAUSAL_DAG",
    "CAUSAL_DAG_PARENTSET_COMMIT",
    "BARDO_PROOF_EDGE_FROZEN",
)


def _generic_invalid_checks(config, context, proof: DagParentCommitProof) -> tuple[int, int]:
    detected = 0
    applicable = 0

    def check(candidate):
        nonlocal detected, applicable
        applicable += 1
        detected += int(not verify_dag_parent_commit(candidate, config, context))

    first = proof.nodes[0]
    phase_after = {"A": "C", "M": "A", "C": "A"}[first.claim.phase_after]
    check(DagParentCommitProof(
        proof.phase_facts,
        proof.stimulus_facts,
        (replace(first, claim=replace(first.claim, phase_after=phase_after)), *proof.nodes[1:]),
    ))

    stimulus = list(proof.stimulus_facts)
    tick, site, value = stimulus[0]
    stimulus[0] = (tick, site, -value if value != 0.0 else 0.1)
    check(DagParentCommitProof(proof.phase_facts, tuple(stimulus), proof.nodes))

    facts = list(proof.phase_facts)
    own = first.claim.site
    pre_tick = first.claim.logical_tick - 1
    target_index = next(
        i for i, fact in enumerate(facts)
        if fact.tick == pre_tick and fact.site != own
    )
    fact = facts[target_index]
    other = {"A": "C", "M": "A", "C": "A"}[fact.phase]
    facts[target_index] = replace(fact, phase=other)
    check(DagParentCommitProof(tuple(facts), proof.stimulus_facts, proof.nodes))

    check(DagParentCommitProof(
        proof.phase_facts,
        proof.stimulus_facts,
        (replace(first, claim=replace(first.claim, logical_tick=first.claim.logical_tick + 97)), *proof.nodes[1:]),
    ))

    parent_index = next((i for i, node in enumerate(proof.nodes) if node.parent_commitment is not None), None)
    if parent_index is not None:
        nodes = list(proof.nodes)
        nodes[parent_index] = replace(nodes[parent_index], parent_commitment=None)
        check(DagParentCommitProof(proof.phase_facts, proof.stimulus_facts, tuple(nodes)))
        nodes = list(proof.nodes)
        nodes[parent_index] = replace(nodes[parent_index], parent_commitment="sha256:" + "0" * 64)
        check(DagParentCommitProof(proof.phase_facts, proof.stimulus_facts, tuple(nodes)))

    return detected, applicable


def build_report() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    totals = {name: {metric: 0 for metric in COST_METRICS} for name in SYSTEMS}
    valid = {name: 0 for name in SYSTEMS}
    invalid_detected = {name: 0 for name in SYSTEMS}
    invalid_applicable = {name: 0 for name in SYSTEMS}
    instances = 0

    for grid_name in manifest["workload"]["grids"]:
        for chain_length in manifest["workload"]["chain_lengths"]:
            for family in manifest["workload"]["seed_families"]:
                for trial in range(manifest["workload"]["trials_per_grid_chain_family"]):
                    config, context, snapshot, local, explicit, bardo = _instance(
                        manifest, grid_name, chain_length, family, trial
                    )
                    claims = tuple(item.claim for item in explicit.claims)
                    generic = DagParentCommitProof(
                        explicit.phase_facts,
                        explicit.stimulus_facts,
                        build_dag_nodes(claims, config),
                    )

                    valid["EXPLICIT_CAUSAL_DAG"] += int(verify_causal_dag(explicit, config, context))
                    valid["CAUSAL_DAG_PARENTSET_COMMIT"] += int(verify_dag_parent_commit(generic, config, context))
                    valid["BARDO_PROOF_EDGE_FROZEN"] += int(verify_bardo_proof(bardo, config, context))

                    metric_sets = {
                        "EXPLICIT_CAUSAL_DAG": proof_metrics(explicit, config),
                        "CAUSAL_DAG_PARENTSET_COMMIT": dag_parent_commit_metrics(generic, config),
                        "BARDO_PROOF_EDGE_FROZEN": bardo_proof_metrics(bardo, config),
                    }
                    for name in SYSTEMS:
                        for metric in COST_METRICS:
                            totals[name][metric] += metric_sets[name][metric]

                    detected, applicable = _generic_invalid_checks(config, context, generic)
                    invalid_detected["CAUSAL_DAG_PARENTSET_COMMIT"] += detected
                    invalid_applicable["CAUSAL_DAG_PARENTSET_COMMIT"] += applicable

                    # Existing BARDO-PROOF-03 runner already exercises the same
                    # six mutation families for explicit DAG and frozen Bardo.
                    from benchmarks.run_bardo_proof_03 import _invalid_checks
                    invalid = _invalid_checks(config, context, snapshot, local, explicit, bardo)
                    for source_name, target_name in (
                        ("CAUSAL_DAG", "EXPLICIT_CAUSAL_DAG"),
                        ("BARDO_PROOF_EDGE", "BARDO_PROOF_EDGE_FROZEN"),
                    ):
                        d, a = invalid[source_name]
                        invalid_detected[target_name] += d
                        invalid_applicable[target_name] += a
                    instances += 1

    if instances != manifest["workload"]["total_queries"]:
        raise RuntimeError(f"expected 192 held-out instances, observed {instances}")

    valid_rate = {name: valid[name] / instances for name in SYSTEMS}
    invalid_rate = {
        name: invalid_detected[name] / invalid_applicable[name]
        for name in SYSTEMS
    }

    def reductions(candidate: str, baseline: str) -> dict[str, float]:
        result = {}
        for metric in COST_METRICS:
            base = totals[baseline][metric]
            cand = totals[candidate][metric]
            result[metric] = 0.0 if base == 0 and cand == 0 else (1.0 - cand / base)
        return result

    generic_vs_explicit = reductions("CAUSAL_DAG_PARENTSET_COMMIT", "EXPLICIT_CAUSAL_DAG")
    bardo_vs_generic = reductions("BARDO_PROOF_EDGE_FROZEN", "CAUSAL_DAG_PARENTSET_COMMIT")
    sound = all(value == 1.0 for value in valid_rate.values()) and all(
        value == 1.0 for value in invalid_rate.values()
    )
    generic_max = max(generic_vs_explicit.values())
    generic_regression = max(max(0.0, -v) for v in generic_vs_explicit.values())
    bardo_max = max(bardo_vs_generic.values())
    bardo_regression = max(max(0.0, -v) for v in bardo_vs_generic.values())

    generic_supported = (
        sound
        and generic_max >= manifest["acceptance"]["generic_parent_commitment_improvement_vs_explicit_min_fraction"]
        and generic_regression <= manifest["acceptance"]["maximum_primary_metric_regression_fraction"]
    )
    bardo_supported = (
        sound
        and bardo_max >= manifest["acceptance"]["bardo_relation_improvement_vs_generic_commit_dag_min_fraction"]
        and bardo_regression <= manifest["acceptance"]["maximum_primary_metric_regression_fraction"]
    )

    if not sound:
        decision = "CONTROL_FAILURE"
    elif bardo_supported:
        decision = "BARDO_RELATION_VALUE_SUPPORTED"
    elif generic_supported:
        decision = "GENERIC_PARENT_COMMITMENT_VALUE_ONLY"
    else:
        decision = "NO_PARENT_COMMITMENT_VALUE"

    return {
        "experiment_id": manifest["experiment_id"],
        "decision": decision,
        "instances": instances,
        "valid_proof_acceptance": valid_rate,
        "invalid_proof_detection": invalid_rate,
        "totals": totals,
        "generic_reduction_vs_explicit": generic_vs_explicit,
        "bardo_reduction_vs_generic": bardo_vs_generic,
        "generic_max_improvement": generic_max,
        "generic_max_regression": generic_regression,
        "bardo_max_improvement": bardo_max,
        "bardo_max_regression": bardo_regression,
        "generic_parent_commitment_supported": generic_supported,
        "bardo_relation_supported": bardo_supported,
        "aggregation": manifest["aggregation"],
        "timing_decisive": False,
        "frozen_bardo_head": manifest["frozen_parent_head"],
    }


def main() -> None:
    print(json.dumps(build_report(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
