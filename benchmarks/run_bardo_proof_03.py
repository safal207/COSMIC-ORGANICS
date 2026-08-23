"""Execute BARDO-PROOF-03/v0.2 on the frozen 192-instance workload."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from math import ceil
from pathlib import Path
import random
from time import perf_counter_ns

from morphos.bardo_proof_edges import (
    BardoProof,
    BardoProofEdge,
    bardo_proof_metrics,
    build_bardo_edges,
    verify_bardo_proof,
)
from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.proof_controls_v02 import (
    CausalDagProof,
    DagClaim,
    LocalWitness,
    LocalWitnessProof,
    SnapshotItem,
    SnapshotLocalProof,
    TransitionClaim,
    VerificationContext,
    _neighbors,
    committed_fact,
    proof_metrics,
    state_root,
    verify_causal_dag,
    verify_local_witness,
    verify_snapshot_local,
)

MANIFEST = Path(__file__).with_name("bardo_proof_03_v02_manifest.json")
SYSTEMS = ("SNAPSHOT_LOCAL", "LOCAL_WITNESS", "CAUSAL_DAG", "BARDO_PROOF_EDGE")
COST_METRICS = (
    "canonical_proof_payload_bytes",
    "unique_phase_facts_disclosed",
    "merkle_sibling_hashes_disclosed",
    "unique_stimulus_facts_disclosed",
    "parent_references_disclosed",
    "local_transition_evaluations",
    "hash_evaluations",
    "proof_objects_traversed",
)


def _grid(text: str) -> tuple[int, int]:
    left, right = text.lower().split("x", 1)
    return int(left), int(right)


def _config(manifest: dict, width: int, height: int) -> Grid2DConfig:
    c = manifest["frozen_config"]
    return Grid2DConfig(width=width, height=height, **c)


def _stable_seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big")


def _query_layers(config: Grid2DConfig, count: int, seed: int) -> list[tuple[int, tuple[int, ...]]]:
    rng = random.Random(seed)
    row = 2 + rng.randrange(max(1, config.height - 4))
    col = 2 + rng.randrange(max(1, config.width - 4))
    center = row * config.width + col
    star = (
        center,
        (row - 1) * config.width + col,
        (row + 1) * config.width + col,
        row * config.width + col - 1,
        row * config.width + col + 1,
    )
    if count == 1:
        return [(1, (center,))]

    layers: list[tuple[int, tuple[int, ...]]] = []
    remaining = count
    tick = 1
    while remaining:
        if remaining == 1 or tick % 2 == 0:
            sites = (center,)
        else:
            width = min(5, max(2, remaining - 1))
            rotation = seed % len(star)
            rotated = star[rotation:] + star[:rotation]
            sites = tuple(rotated[:width])
        if len(sites) > remaining:
            sites = sites[:remaining]
        layers.append((tick, sites))
        remaining -= len(sites)
        tick += 1
    return layers


def _initial_state(cells: int, seed: int) -> str:
    rng = random.Random(seed)
    return "".join("C" if rng.random() < 0.25 else "A" for _ in range(cells))


def _instance(manifest: dict, grid_name: str, chain_length: int, family: int, trial: int):
    width, height = _grid(grid_name)
    config = _config(manifest, width, height)
    cells = width * height
    seed = _stable_seed(family, grid_name, chain_length, trial)
    layers = _query_layers(config, chain_length, seed)
    model = Grid2D(_initial_state(cells, seed), config=config)

    states_by_pre_tick: dict[int, str] = {}
    claims: list[TransitionClaim] = []
    stimuli: list[tuple[int, int, float]] = []
    query_order: list[tuple[int, int]] = []
    pulse_magnitude = manifest["workload"]["pulse_magnitude"]
    active_count = max(1, ceil(cells * manifest["workload"]["activity_density"]))

    for tick, query_sites in layers:
        before = model.state_string()
        states_by_pre_tick[tick - 1] = before
        pulse = [0.0] * cells
        rng = random.Random(_stable_seed(seed, tick, "pulse"))
        active = set(rng.sample(range(cells), min(cells, active_count)))
        active.update(query_sites)
        for site in sorted(active):
            sign = 1.0 if _stable_seed(seed, tick, site) % 2 == 0 else -1.0
            pulse[site] = sign * pulse_magnitude
        model.step(pulse)
        after = model.state_string()
        for site in query_sites:
            claim = TransitionClaim(tick, site, after[site])
            claims.append(claim)
            query_order.append((tick, site))
            stimuli.append((tick, site, float(pulse[site])))

    context = VerificationContext(
        expected_queries=tuple(query_order),
        state_roots=tuple(
            (tick, state_root(state)) for tick, state in sorted(states_by_pre_tick.items())
        ),
        expected_stimuli=tuple(stimuli),
    )

    snapshot_items = []
    local_witnesses = []
    fact_map = {}
    stimulus_map = {(tick, site): value for tick, site, value in stimuli}
    for claim in claims:
        pre_tick = claim.logical_tick - 1
        state = states_by_pre_tick[pre_tick]
        stimulus = stimulus_map[(claim.logical_tick, claim.site)]
        snapshot_items.append(SnapshotItem(claim, state, stimulus))
        neighbors = _neighbors(claim.site, config)
        own = committed_fact(state, pre_tick, claim.site)
        neighbor_facts = tuple(committed_fact(state, pre_tick, site) for site in neighbors)
        local_witnesses.append(LocalWitness(claim, own, neighbor_facts, stimulus))
        fact_map[(pre_tick, claim.site)] = own
        for fact in neighbor_facts:
            fact_map[(fact.tick, fact.site)] = fact

    phase_facts = tuple(fact_map[key] for key in sorted(fact_map))
    snapshot = SnapshotLocalProof(tuple(snapshot_items))
    local = LocalWitnessProof(tuple(local_witnesses))

    claim_by_tick_site = {(claim.logical_tick, claim.site): claim for claim in claims}
    dag_claims = []
    for claim in claims:
        pre_tick = claim.logical_tick - 1
        parent_ids = []
        for site in (claim.site, *_neighbors(claim.site, config)):
            parent = claim_by_tick_site.get((pre_tick, site))
            if parent is not None:
                parent_ids.append(parent.claim_id)
        dag_claims.append(DagClaim(claim, tuple(sorted(parent_ids))))
    dag = CausalDagProof(phase_facts, tuple(stimuli), tuple(dag_claims))
    bardo = BardoProof(phase_facts, tuple(stimuli), build_bardo_edges(claims, config))

    return config, context, snapshot, local, dag, bardo


def _alternate_phase(phase: str) -> str:
    return {"A": "C", "M": "A", "C": "A"}[phase]


def _invalid_checks(config, context, snapshot, local, dag, bardo) -> dict[str, tuple[int, int]]:
    detected = {name: 0 for name in SYSTEMS}
    applicable = {name: 0 for name in SYSTEMS}

    verifiers = {
        "SNAPSHOT_LOCAL": lambda proof: verify_snapshot_local(proof, config, context),
        "LOCAL_WITNESS": lambda proof: verify_local_witness(proof, config, context),
        "CAUSAL_DAG": lambda proof: verify_causal_dag(proof, config, context),
        "BARDO_PROOF_EDGE": lambda proof: verify_bardo_proof(proof, config, context),
    }

    def check(name, proof):
        applicable[name] += 1
        detected[name] += int(not verifiers[name](proof))

    # wrong_next_phase
    item = snapshot.items[0]
    wrong_claim = replace(item.claim, phase_after=_alternate_phase(item.claim.phase_after))
    check("SNAPSHOT_LOCAL", SnapshotLocalProof((replace(item, claim=wrong_claim), *snapshot.items[1:])))
    witness = local.witnesses[0]
    check("LOCAL_WITNESS", LocalWitnessProof((replace(witness, claim=wrong_claim), *local.witnesses[1:])))
    dag_first = dag.claims[0]
    check("CAUSAL_DAG", CausalDagProof(dag.phase_facts, dag.stimulus_facts, (replace(dag_first, claim=wrong_claim), *dag.claims[1:])))
    edge = bardo.edges[0]
    check("BARDO_PROOF_EDGE", BardoProof(bardo.phase_facts, bardo.stimulus_facts, (replace(edge, claim=wrong_claim), *bardo.edges[1:])))

    # mutated_local_stimulus
    changed = -item.local_stimulus if item.local_stimulus != 0.0 else 0.1
    check("SNAPSHOT_LOCAL", SnapshotLocalProof((replace(item, local_stimulus=changed), *snapshot.items[1:])))
    check("LOCAL_WITNESS", LocalWitnessProof((replace(witness, local_stimulus=changed), *local.witnesses[1:])))
    stimulus = list(dag.stimulus_facts)
    t, s, v = stimulus[0]
    stimulus[0] = (t, s, -v if v != 0.0 else 0.1)
    check("CAUSAL_DAG", CausalDagProof(dag.phase_facts, tuple(stimulus), dag.claims))
    check("BARDO_PROOF_EDGE", BardoProof(bardo.phase_facts, tuple(stimulus), bardo.edges))

    # mutated_neighbor_phase, reusing the original auth path/root.
    first_neighbor = local.witnesses[0].neighbors[0]
    mutated_fact = replace(first_neighbor, phase=_alternate_phase(first_neighbor.phase))
    local_neighbors = (mutated_fact, *local.witnesses[0].neighbors[1:])
    check("LOCAL_WITNESS", LocalWitnessProof((replace(witness, neighbors=local_neighbors), *local.witnesses[1:])))
    facts = list(dag.phase_facts)
    for index, fact in enumerate(facts):
        if (fact.tick, fact.site) == (first_neighbor.tick, first_neighbor.site):
            facts[index] = mutated_fact
            break
    check("CAUSAL_DAG", CausalDagProof(tuple(facts), dag.stimulus_facts, dag.claims))
    check("BARDO_PROOF_EDGE", BardoProof(tuple(facts), bardo.stimulus_facts, bardo.edges))
    state_chars = list(item.pre_tick_state)
    state_chars[first_neighbor.site] = _alternate_phase(state_chars[first_neighbor.site])
    check("SNAPSHOT_LOCAL", SnapshotLocalProof((replace(item, pre_tick_state="".join(state_chars)), *snapshot.items[1:])))

    # wrong_logical_tick
    tick_claim = replace(item.claim, logical_tick=item.claim.logical_tick + 97)
    check("SNAPSHOT_LOCAL", SnapshotLocalProof((replace(item, claim=tick_claim), *snapshot.items[1:])))
    check("LOCAL_WITNESS", LocalWitnessProof((replace(witness, claim=tick_claim), *local.witnesses[1:])))
    check("CAUSAL_DAG", CausalDagProof(dag.phase_facts, dag.stimulus_facts, (replace(dag_first, claim=tick_claim), *dag.claims[1:])))
    check("BARDO_PROOF_EDGE", BardoProof(bardo.phase_facts, bardo.stimulus_facts, (replace(edge, claim=tick_claim), *bardo.edges[1:])))

    # missing/substituted parent are applicable to causal graph systems when a
    # queried edge actually has parents.
    parent_index = next((i for i, claim in enumerate(dag.claims) if claim.parent_ids), None)
    if parent_index is not None:
        dag_items = list(dag.claims)
        dag_items[parent_index] = replace(dag_items[parent_index], parent_ids=())
        check("CAUSAL_DAG", CausalDagProof(dag.phase_facts, dag.stimulus_facts, tuple(dag_items)))
        bardo_edges = list(bardo.edges)
        bardo_edges[parent_index] = replace(bardo_edges[parent_index], parent_commitment=None)
        check("BARDO_PROOF_EDGE", BardoProof(bardo.phase_facts, bardo.stimulus_facts, tuple(bardo_edges)))

        dag_items = list(dag.claims)
        dag_items[parent_index] = replace(dag_items[parent_index], parent_ids=("sha256:" + "0" * 64,))
        check("CAUSAL_DAG", CausalDagProof(dag.phase_facts, dag.stimulus_facts, tuple(dag_items)))
        bardo_edges = list(bardo.edges)
        bardo_edges[parent_index] = replace(bardo_edges[parent_index], parent_commitment="sha256:" + "0" * 64)
        check("BARDO_PROOF_EDGE", BardoProof(bardo.phase_facts, bardo.stimulus_facts, tuple(bardo_edges)))

    return {name: (detected[name], applicable[name]) for name in SYSTEMS}


def build_report() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    totals = {name: {metric: 0 for metric in COST_METRICS} for name in SYSTEMS}
    valid = {name: 0 for name in SYSTEMS}
    invalid_detected = {name: 0 for name in SYSTEMS}
    invalid_applicable = {name: 0 for name in SYSTEMS}
    runtime_ns = {name: 0 for name in SYSTEMS}
    instances = 0

    for grid_name in manifest["workload"]["grids"]:
        for chain_length in manifest["workload"]["chain_lengths"]:
            for family in manifest["workload"]["seed_families"]:
                for trial in range(manifest["workload"]["trials_per_grid_chain_family"]):
                    config, context, snapshot, local, dag, bardo = _instance(
                        manifest, grid_name, chain_length, family, trial
                    )
                    proofs = {
                        "SNAPSHOT_LOCAL": snapshot,
                        "LOCAL_WITNESS": local,
                        "CAUSAL_DAG": dag,
                        "BARDO_PROOF_EDGE": bardo,
                    }
                    verify = {
                        "SNAPSHOT_LOCAL": verify_snapshot_local,
                        "LOCAL_WITNESS": verify_local_witness,
                        "CAUSAL_DAG": verify_causal_dag,
                        "BARDO_PROOF_EDGE": verify_bardo_proof,
                    }
                    metrics = {
                        "SNAPSHOT_LOCAL": proof_metrics(snapshot, config),
                        "LOCAL_WITNESS": proof_metrics(local, config),
                        "CAUSAL_DAG": proof_metrics(dag, config),
                        "BARDO_PROOF_EDGE": bardo_proof_metrics(bardo, config),
                    }
                    for name in SYSTEMS:
                        started = perf_counter_ns()
                        accepted = verify[name](proofs[name], config, context)
                        runtime_ns[name] += perf_counter_ns() - started
                        valid[name] += int(accepted)
                        for metric in COST_METRICS:
                            totals[name][metric] += metrics[name][metric]

                    invalid = _invalid_checks(config, context, snapshot, local, dag, bardo)
                    for name, (detected, applicable) in invalid.items():
                        invalid_detected[name] += detected
                        invalid_applicable[name] += applicable
                    instances += 1

    expected_instances = manifest["workload"]["total_queries"]
    if instances != expected_instances:
        raise RuntimeError(f"expected {expected_instances} proof instances, observed {instances}")

    valid_rate = {name: valid[name] / instances for name in SYSTEMS}
    invalid_rate = {
        name: invalid_detected[name] / invalid_applicable[name]
        if invalid_applicable[name]
        else 0.0
        for name in SYSTEMS
    }

    def reduction(candidate: str, baseline: str, metric: str) -> float:
        base = totals[baseline][metric]
        cand = totals[candidate][metric]
        if base == 0:
            return 0.0 if cand == 0 else float("-inf")
        return 1.0 - cand / base

    local_payload_reduction = reduction("LOCAL_WITNESS", "SNAPSHOT_LOCAL", "canonical_proof_payload_bytes")
    dag_reductions = {
        metric: reduction("CAUSAL_DAG", "LOCAL_WITNESS", metric) for metric in COST_METRICS
    }
    bardo_reductions = {
        metric: reduction("BARDO_PROOF_EDGE", "CAUSAL_DAG", metric) for metric in COST_METRICS
    }

    sound = all(rate == 1.0 for rate in valid_rate.values()) and all(
        rate == 1.0 for rate in invalid_rate.values()
    )
    local_supported = local_payload_reduction >= manifest["acceptance"]["local_proof_payload_reduction_vs_snapshot_min_fraction"]
    dag_supported = max(dag_reductions.values()) >= manifest["acceptance"]["causal_dag_payload_or_work_reduction_vs_local_min_fraction"]
    bardo_improvement = max(bardo_reductions.values())
    bardo_regression = max(max(0.0, -value) for value in bardo_reductions.values())
    bardo_supported = (
        sound
        and bardo_improvement >= manifest["acceptance"]["bardo_specific_improvement_vs_causal_dag_min_fraction"]
        and bardo_regression <= manifest["acceptance"]["maximum_primary_metric_regression_fraction_for_bardo"]
    )

    if not sound:
        decision = "CONTROL_FAILURE"
    elif bardo_supported:
        decision = "BARDO_PROOF_VALUE_SUPPORTED"
    elif dag_supported:
        decision = "CAUSAL_DAG_VALUE_ONLY"
    elif local_supported:
        decision = "LOCAL_PROOF_VALUE_ONLY"
    else:
        decision = "NO_PROOF_LOCALITY_VALUE"

    return {
        "experiment_id": manifest["experiment_id"],
        "decision": decision,
        "instances": instances,
        "valid_proof_acceptance": valid_rate,
        "invalid_proof_detection": invalid_rate,
        "invalid_cases_applicable": invalid_applicable,
        "totals": totals,
        "verification_runtime_ns": runtime_ns,
        "local_payload_reduction_vs_snapshot": local_payload_reduction,
        "causal_dag_reduction_vs_local": dag_reductions,
        "bardo_reduction_vs_causal_dag": bardo_reductions,
        "bardo_max_improvement": bardo_improvement,
        "bardo_max_regression": bardo_regression,
        "local_supported": local_supported,
        "causal_dag_supported": dag_supported,
        "bardo_specific_supported": bardo_supported,
        "aggregation": "totals_across_all_192_frozen_instances",
        "timing_decisive": False,
    }


def main() -> None:
    report = build_report()
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
