import unittest

from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.proof_controls import (
    CausalDagProof,
    DagClaim,
    LocalWitness,
    LocalWitnessProof,
    SnapshotItem,
    SnapshotLocalProof,
    TransitionClaim,
    proof_metrics,
    verify_causal_dag,
    verify_local_witness,
    verify_snapshot_local,
)


class ProofControlTests(unittest.TestCase):
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

    def _two_tick_trace(self):
        model = Grid2D("A" * 25, config=self.config)
        before1 = model.state_string()
        pulse = [0.0] * 25
        pulse[self.site] = 0.9
        model.step(pulse)
        after1 = model.state_string()
        before2 = after1
        model.step([0.0] * 25)
        after2 = model.state_string()
        self.assertEqual(after1[self.site], "M")
        self.assertEqual(after2[self.site], "A")
        return before1, after1, before2, after2

    def test_snapshot_and_local_witness_accept_same_valid_transition(self):
        before1, after1, _, _ = self._two_tick_trace()
        claim = TransitionClaim(1, self.site, after1[self.site])
        snapshot = SnapshotLocalProof((SnapshotItem(claim, before1, 0.9),))
        local = LocalWitnessProof(
            (
                LocalWitness(
                    claim,
                    before1[self.site],
                    tuple((site, before1[site]) for site in self.neighbors),
                    0.9,
                ),
            )
        )
        query = [(1, self.site)]
        self.assertTrue(verify_snapshot_local(snapshot, self.config, query))
        self.assertTrue(verify_local_witness(local, self.config, query))
        self.assertLess(
            proof_metrics(local, self.config)["canonical_proof_payload_bytes"],
            proof_metrics(snapshot, self.config)["canonical_proof_payload_bytes"],
        )

    def test_wrong_next_phase_is_rejected(self):
        before1, _, _, _ = self._two_tick_trace()
        wrong = TransitionClaim(1, self.site, "C")
        snapshot = SnapshotLocalProof((SnapshotItem(wrong, before1, 0.9),))
        local = LocalWitnessProof(
            (
                LocalWitness(
                    wrong,
                    before1[self.site],
                    tuple((site, before1[site]) for site in self.neighbors),
                    0.9,
                ),
            )
        )
        query = [(1, self.site)]
        self.assertFalse(verify_snapshot_local(snapshot, self.config, query))
        self.assertFalse(verify_local_witness(local, self.config, query))

    def test_mutated_stimulus_neighbor_and_tick_are_rejected(self):
        before1, after1, _, _ = self._two_tick_trace()
        claim = TransitionClaim(1, self.site, after1[self.site])
        query = [(1, self.site)]

        bad_stimulus = LocalWitnessProof(
            (
                LocalWitness(
                    claim,
                    before1[self.site],
                    tuple((site, before1[site]) for site in self.neighbors),
                    -0.9,
                ),
            )
        )
        self.assertFalse(verify_local_witness(bad_stimulus, self.config, query))

        mutated_neighbors = [(site, before1[site]) for site in self.neighbors]
        mutated_neighbors[0] = (mutated_neighbors[0][0], "C")
        bad_neighbor = LocalWitnessProof(
            (
                LocalWitness(
                    claim,
                    before1[self.site],
                    tuple(mutated_neighbors),
                    0.9,
                ),
            )
        )
        self.assertFalse(verify_local_witness(bad_neighbor, self.config, query))

        wrong_tick = TransitionClaim(2, self.site, after1[self.site])
        bad_tick = LocalWitnessProof(
            (
                LocalWitness(
                    wrong_tick,
                    before1[self.site],
                    tuple((site, before1[site]) for site in self.neighbors),
                    0.9,
                ),
            )
        )
        self.assertFalse(verify_local_witness(bad_tick, self.config, query))

    def _valid_two_claim_dag(self):
        before1, after1, before2, after2 = self._two_tick_trace()
        claim1 = TransitionClaim(1, self.site, after1[self.site])
        claim2 = TransitionClaim(2, self.site, after2[self.site])
        phase_facts = []
        for tick, state in ((0, before1), (1, before2)):
            for site in (self.site, *self.neighbors):
                phase_facts.append((tick, site, state[site]))
        proof = CausalDagProof(
            phase_facts=tuple(sorted(set(phase_facts))),
            stimulus_facts=((1, self.site, 0.9), (2, self.site, 0.0)),
            claims=(
                DagClaim(claim1, ()),
                DagClaim(claim2, (claim1.claim_id,)),
            ),
        )
        return proof, [(1, self.site), (2, self.site)]

    def test_causal_dag_accepts_composing_parent(self):
        proof, queries = self._valid_two_claim_dag()
        self.assertTrue(verify_causal_dag(proof, self.config, queries))

    def test_causal_dag_rejects_missing_parent(self):
        proof, queries = self._valid_two_claim_dag()
        mutated = CausalDagProof(
            phase_facts=proof.phase_facts,
            stimulus_facts=proof.stimulus_facts,
            claims=(proof.claims[0], DagClaim(proof.claims[1].claim, ())),
        )
        self.assertFalse(verify_causal_dag(mutated, self.config, queries))

    def test_causal_dag_rejects_substituted_parent_identity(self):
        proof, queries = self._valid_two_claim_dag()
        mutated = CausalDagProof(
            phase_facts=proof.phase_facts,
            stimulus_facts=proof.stimulus_facts,
            claims=(
                proof.claims[0],
                DagClaim(proof.claims[1].claim, ("sha256:" + "0" * 64,)),
            ),
        )
        self.assertFalse(verify_causal_dag(mutated, self.config, queries))

    def test_causal_dag_rejects_mutated_disclosed_fact(self):
        proof, queries = self._valid_two_claim_dag()
        facts = list(proof.phase_facts)
        for index, fact in enumerate(facts):
            if fact[:2] == (0, self.neighbors[0]):
                facts[index] = (fact[0], fact[1], "C")
                break
        mutated = CausalDagProof(
            phase_facts=tuple(facts),
            stimulus_facts=proof.stimulus_facts,
            claims=proof.claims,
        )
        self.assertFalse(verify_causal_dag(mutated, self.config, queries))


if __name__ == "__main__":
    unittest.main()
