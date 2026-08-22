import unittest

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
    committed_fact,
    proof_metrics,
    state_root,
    verify_causal_dag,
    verify_local_witness,
    verify_snapshot_local,
)


class ProofControlV02Tests(unittest.TestCase):
    def setUp(self):
        self.config = Grid2DConfig(
            width=5,
            height=5,
            memory_decay=0.0,
            anchor_threshold=0.5,
            adaptive_threshold=0.35,
            anchor_coupling=0.75,
            adaptive_coupling=0.5,
            mixed_relax_threshold=0.05,
            mask="checkerboard",
            neighborhood="von_neumann",
        )
        self.site = 12
        self.neighbors = (7, 17, 11, 13)

    def _trace(self):
        model = Grid2D("A" * 25, config=self.config)
        before1 = model.state_string()
        pulse = [0.0] * 25
        pulse[self.site] = 0.9
        model.step(pulse)
        before2 = model.state_string()
        model.step([0.0] * 25)
        after2 = model.state_string()
        self.assertEqual(before2[self.site], "M")
        self.assertEqual(after2[self.site], "A")
        return before1, before2, after2

    def _context(self, before1, before2, queries=((1, 12), (2, 12))):
        return VerificationContext(
            expected_queries=tuple(queries),
            state_roots=((0, state_root(before1)), (1, state_root(before2))),
            expected_stimuli=((1, self.site, 0.9), (2, self.site, 0.0)),
        )

    def _local_witness(self, claim, state, tick, stimulus):
        return LocalWitness(
            claim=claim,
            phase_before=committed_fact(state, tick - 1, claim.site),
            neighbors=tuple(
                committed_fact(state, tick - 1, site) for site in self.neighbors
            ),
            local_stimulus=stimulus,
        )

    def _valid_controls(self):
        before1, before2, after2 = self._trace()
        claim1 = TransitionClaim(1, self.site, before2[self.site])
        claim2 = TransitionClaim(2, self.site, after2[self.site])
        context = self._context(before1, before2)

        snapshot = SnapshotLocalProof(
            (
                SnapshotItem(claim1, before1, 0.9),
                SnapshotItem(claim2, before2, 0.0),
            )
        )
        local = LocalWitnessProof(
            (
                self._local_witness(claim1, before1, 1, 0.9),
                self._local_witness(claim2, before2, 2, 0.0),
            )
        )

        fact_map = {}
        for tick, state in ((0, before1), (1, before2)):
            for site in (self.site, *self.neighbors):
                fact_map[(tick, site)] = committed_fact(state, tick, site)
        dag = CausalDagProof(
            phase_facts=tuple(fact_map[key] for key in sorted(fact_map)),
            stimulus_facts=((1, self.site, 0.9), (2, self.site, 0.0)),
            claims=(
                DagClaim(claim1, ()),
                DagClaim(claim2, (claim1.claim_id,)),
            ),
        )
        return before1, before2, context, snapshot, local, dag

    def test_valid_controls_accept(self):
        _, _, context, snapshot, local, dag = self._valid_controls()
        self.assertTrue(verify_snapshot_local(snapshot, self.config, context))
        self.assertTrue(verify_local_witness(local, self.config, context))
        self.assertTrue(verify_causal_dag(dag, self.config, context))

    def test_semantics_preserving_neighbor_mutation_is_rejected_by_commitment(self):
        _, _, context, _, local, _ = self._valid_controls()
        witness = local.witnesses[0]
        facts = list(witness.neighbors)
        original = facts[0]
        # Reuse the original authentication path with a substituted phase. The
        # local next phase can remain M under this mutation, so rejection must
        # come from commitment binding rather than transition-law coincidence.
        facts[0] = type(original)(
            tick=original.tick,
            site=original.site,
            phase="C",
            auth_path=original.auth_path,
        )
        mutated = LocalWitnessProof(
            (
                LocalWitness(
                    claim=witness.claim,
                    phase_before=witness.phase_before,
                    neighbors=tuple(facts),
                    local_stimulus=witness.local_stimulus,
                ),
                local.witnesses[1],
            )
        )
        self.assertFalse(verify_local_witness(mutated, self.config, context))

    def test_mutated_stimulus_is_rejected_by_public_context(self):
        _, _, context, _, local, _ = self._valid_controls()
        first = local.witnesses[0]
        mutated = LocalWitnessProof(
            (
                LocalWitness(
                    claim=first.claim,
                    phase_before=first.phase_before,
                    neighbors=first.neighbors,
                    local_stimulus=-0.9,
                ),
                local.witnesses[1],
            )
        )
        self.assertFalse(verify_local_witness(mutated, self.config, context))

    def test_wrong_next_phase_and_tick_are_rejected(self):
        before1, before2, context, _, _, _ = self._valid_controls()
        wrong_phase = TransitionClaim(1, self.site, "C")
        proof = SnapshotLocalProof(
            (
                SnapshotItem(wrong_phase, before1, 0.9),
                SnapshotItem(TransitionClaim(2, self.site, "A"), before2, 0.0),
            )
        )
        self.assertFalse(verify_snapshot_local(proof, self.config, context))

        wrong_tick_claim = TransitionClaim(3, self.site, "M")
        bad_context_order = SnapshotLocalProof(
            (
                SnapshotItem(wrong_tick_claim, before1, 0.9),
                SnapshotItem(TransitionClaim(2, self.site, "A"), before2, 0.0),
            )
        )
        self.assertFalse(verify_snapshot_local(bad_context_order, self.config, context))

    def test_dag_missing_and_substituted_parent_are_rejected(self):
        _, _, context, _, _, dag = self._valid_controls()
        missing = CausalDagProof(
            phase_facts=dag.phase_facts,
            stimulus_facts=dag.stimulus_facts,
            claims=(dag.claims[0], DagClaim(dag.claims[1].claim, ())),
        )
        self.assertFalse(verify_causal_dag(missing, self.config, context))

        substituted = CausalDagProof(
            phase_facts=dag.phase_facts,
            stimulus_facts=dag.stimulus_facts,
            claims=(
                dag.claims[0],
                DagClaim(dag.claims[1].claim, ("sha256:" + "0" * 64,)),
            ),
        )
        self.assertFalse(verify_causal_dag(substituted, self.config, context))

    def test_dag_mutated_phase_fact_is_rejected_even_if_law_result_survives(self):
        _, _, context, _, _, dag = self._valid_controls()
        facts = list(dag.phase_facts)
        for index, fact in enumerate(facts):
            if (fact.tick, fact.site) == (0, self.neighbors[0]):
                facts[index] = type(fact)(
                    tick=fact.tick,
                    site=fact.site,
                    phase="C",
                    auth_path=fact.auth_path,
                )
                break
        mutated = CausalDagProof(tuple(facts), dag.stimulus_facts, dag.claims)
        self.assertFalse(verify_causal_dag(mutated, self.config, context))

    def test_metrics_are_deterministic_and_local_payload_is_smaller_on_real_grid_scale(self):
        # The preregistered grids begin at 16x16; use that scale for the payload
        # sanity check rather than a tiny 5x5 fixture where JSON key overhead can
        # dominate the full-state string.
        config = Grid2DConfig(width=16, height=16, memory_decay=0.0)
        site = 136
        state = "A" * 256
        model = Grid2D(state, config=config)
        pulse = [0.0] * 256
        pulse[site] = 0.9
        model.step(pulse)
        claim = TransitionClaim(1, site, model.state_string()[site])
        context = VerificationContext(
            expected_queries=((1, site),),
            state_roots=((0, state_root(state)),),
            expected_stimuli=((1, site, 0.9),),
        )
        snapshot = SnapshotLocalProof((SnapshotItem(claim, state, 0.9),))
        neighbor_sites = (120, 152, 135, 137)
        local = LocalWitnessProof(
            (
                LocalWitness(
                    claim,
                    committed_fact(state, 0, site),
                    tuple(committed_fact(state, 0, item) for item in neighbor_sites),
                    0.9,
                ),
            )
        )
        self.assertTrue(verify_snapshot_local(snapshot, config, context))
        self.assertTrue(verify_local_witness(local, config, context))
        first = proof_metrics(local, config)
        second = proof_metrics(local, config)
        self.assertEqual(first, second)
        self.assertLess(
            first["unique_phase_facts_disclosed"],
            proof_metrics(snapshot, config)["unique_phase_facts_disclosed"],
        )


if __name__ == "__main__":
    unittest.main()
