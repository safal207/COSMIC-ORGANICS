import unittest

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
    TransitionClaim,
    VerificationContext,
    committed_fact,
    proof_metrics,
    state_root,
    verify_causal_dag,
)


class BardoProofEdgeTests(unittest.TestCase):
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

    def _valid_pair(self):
        model = Grid2D("A" * 25, config=self.config)
        before1 = model.state_string()
        pulse = [0.0] * 25
        pulse[self.site] = 0.9
        model.step(pulse)
        before2 = model.state_string()
        model.step([0.0] * 25)
        after2 = model.state_string()

        claims = (
            TransitionClaim(1, self.site, before2[self.site]),
            TransitionClaim(2, self.site, after2[self.site]),
        )
        context = VerificationContext(
            expected_queries=((1, self.site), (2, self.site)),
            state_roots=((0, state_root(before1)), (1, state_root(before2))),
            expected_stimuli=((1, self.site, 0.9), (2, self.site, 0.0)),
        )
        facts = {}
        for tick, state in ((0, before1), (1, before2)):
            for site in (self.site, *self.neighbors):
                facts[(tick, site)] = committed_fact(state, tick, site)
        proof = BardoProof(
            phase_facts=tuple(facts[key] for key in sorted(facts)),
            stimulus_facts=((1, self.site, 0.9), (2, self.site, 0.0)),
            edges=build_bardo_edges(claims, self.config),
        )
        return before1, before2, context, proof

    def test_valid_proof_accepts(self):
        _, _, context, proof = self._valid_pair()
        self.assertTrue(verify_bardo_proof(proof, self.config, context))

    def test_missing_and_substituted_parent_commitment_reject(self):
        _, _, context, proof = self._valid_pair()
        first, second = proof.edges
        missing = BardoProof(
            proof.phase_facts,
            proof.stimulus_facts,
            (first, BardoProofEdge(second.claim, first.parent_commitment)),
        )
        self.assertFalse(verify_bardo_proof(missing, self.config, context))

        substituted = BardoProof(
            proof.phase_facts,
            proof.stimulus_facts,
            (first, BardoProofEdge(second.claim, "sha256:" + "0" * 64)),
        )
        self.assertFalse(verify_bardo_proof(substituted, self.config, context))

    def test_mutated_committed_neighbor_rejects_even_if_transition_can_survive(self):
        _, _, context, proof = self._valid_pair()
        facts = list(proof.phase_facts)
        for index, fact in enumerate(facts):
            if (fact.tick, fact.site) == (0, self.neighbors[0]):
                facts[index] = type(fact)(
                    tick=fact.tick,
                    site=fact.site,
                    phase="C",
                    auth_path=fact.auth_path,
                )
                break
        mutated = BardoProof(tuple(facts), proof.stimulus_facts, proof.edges)
        self.assertFalse(verify_bardo_proof(mutated, self.config, context))

    def test_mutated_stimulus_wrong_phase_and_wrong_tick_reject(self):
        _, _, context, proof = self._valid_pair()
        bad_stimulus = BardoProof(
            proof.phase_facts,
            ((1, self.site, -0.9), (2, self.site, 0.0)),
            proof.edges,
        )
        self.assertFalse(verify_bardo_proof(bad_stimulus, self.config, context))

        claims = [edge.claim for edge in proof.edges]
        claims[0] = TransitionClaim(1, self.site, "C")
        bad_phase = BardoProof(
            proof.phase_facts,
            proof.stimulus_facts,
            build_bardo_edges(claims, self.config),
        )
        self.assertFalse(verify_bardo_proof(bad_phase, self.config, context))

        claims = [edge.claim for edge in proof.edges]
        claims[0] = TransitionClaim(3, self.site, claims[0].phase_after)
        bad_tick = BardoProof(
            proof.phase_facts,
            proof.stimulus_facts,
            build_bardo_edges(claims, self.config),
        )
        self.assertFalse(verify_bardo_proof(bad_tick, self.config, context))

    def test_metrics_are_deterministic(self):
        _, _, _, proof = self._valid_pair()
        self.assertEqual(
            bardo_proof_metrics(proof, self.config),
            bardo_proof_metrics(proof, self.config),
        )

    def test_parent_set_commitment_compacts_multi_parent_control(self):
        model = Grid2D("A" * 25, config=self.config)
        before1 = model.state_string()
        pulse1 = [0.0] * 25
        for site in (self.site, 7, 11):
            pulse1[site] = 0.9
        model.step(pulse1)
        before2 = model.state_string()
        pulse2 = [0.0] * 25
        pulse2[self.site] = -0.9
        model.step(pulse2)
        after2 = model.state_string()

        claims = (
            TransitionClaim(1, self.site, before2[self.site]),
            TransitionClaim(1, 7, before2[7]),
            TransitionClaim(1, 11, before2[11]),
            TransitionClaim(2, self.site, after2[self.site]),
        )
        queries = tuple((c.logical_tick, c.site) for c in claims)
        context = VerificationContext(
            expected_queries=queries,
            state_roots=((0, state_root(before1)), (1, state_root(before2))),
            expected_stimuli=((1, self.site, 0.9), (1, 7, 0.9), (1, 11, 0.9), (2, self.site, -0.9)),
        )
        facts = {}
        for claim in claims:
            state = before1 if claim.logical_tick == 1 else before2
            tick = claim.logical_tick - 1
            row, col = divmod(claim.site, self.config.width)
            sites = [claim.site]
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = row + dr, col + dc
                if 0 <= rr < self.config.height and 0 <= cc < self.config.width:
                    sites.append(rr * self.config.width + cc)
            for site in sites:
                facts[(tick, site)] = committed_fact(state, tick, site)
        phase_facts = tuple(facts[key] for key in sorted(facts))
        stimuli = context.expected_stimuli

        bardo = BardoProof(phase_facts, stimuli, build_bardo_edges(claims, self.config))
        self.assertTrue(verify_bardo_proof(bardo, self.config, context))

        claim_map = {(c.logical_tick, c.site): c for c in claims}
        dag_claims = []
        for claim in claims:
            parent_ids = []
            if claim.logical_tick > 1:
                for site in (claim.site, 7, 17, 11, 13):
                    parent = claim_map.get((claim.logical_tick - 1, site))
                    if parent is not None:
                        parent_ids.append(parent.claim_id)
            dag_claims.append(DagClaim(claim, tuple(parent_ids)))
        dag = CausalDagProof(phase_facts, stimuli, tuple(dag_claims))
        self.assertTrue(verify_causal_dag(dag, self.config, context))
        self.assertLess(
            bardo_proof_metrics(bardo, self.config)["parent_references_disclosed"],
            proof_metrics(dag, self.config)["parent_references_disclosed"],
        )


if __name__ == "__main__":
    unittest.main()
