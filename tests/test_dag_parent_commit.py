import unittest

from morphos.bardo_proof_edges import BardoProof, bardo_proof_metrics, build_bardo_edges, verify_bardo_proof
from morphos.dag_parent_commit import (
    DagParentCommitProof,
    build_dag_nodes,
    dag_parent_commit_metrics,
    verify_dag_parent_commit,
)
from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.proof_controls_v02 import TransitionClaim, VerificationContext, committed_fact, state_root


class GenericParentCommitDagTests(unittest.TestCase):
    def test_generic_control_matches_frozen_bardo_information_and_cost_counts(self):
        config = Grid2DConfig(width=5, height=5, memory_decay=0.0)
        model = Grid2D("A" * 25, config=config)
        before1 = model.state_string()
        pulse1 = [0.0] * 25
        for site in (12, 7, 11):
            pulse1[site] = 0.9
        model.step(pulse1)
        before2 = model.state_string()
        pulse2 = [0.0] * 25
        pulse2[12] = -0.9
        model.step(pulse2)
        after2 = model.state_string()

        claims = (
            TransitionClaim(1, 12, before2[12]),
            TransitionClaim(1, 7, before2[7]),
            TransitionClaim(1, 11, before2[11]),
            TransitionClaim(2, 12, after2[12]),
        )
        stimuli = ((1, 12, 0.9), (1, 7, 0.9), (1, 11, 0.9), (2, 12, -0.9))
        context = VerificationContext(
            expected_queries=tuple((c.logical_tick, c.site) for c in claims),
            state_roots=((0, state_root(before1)), (1, state_root(before2))),
            expected_stimuli=stimuli,
        )
        facts = {}
        for claim in claims:
            state = before1 if claim.logical_tick == 1 else before2
            tick = claim.logical_tick - 1
            row, col = divmod(claim.site, config.width)
            sites = [claim.site]
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = row + dr, col + dc
                if 0 <= rr < config.height and 0 <= cc < config.width:
                    sites.append(rr * config.width + cc)
            for site in sites:
                facts[(tick, site)] = committed_fact(state, tick, site)
        phase_facts = tuple(facts[key] for key in sorted(facts))

        generic = DagParentCommitProof(phase_facts, stimuli, build_dag_nodes(claims, config))
        bardo = BardoProof(phase_facts, stimuli, build_bardo_edges(claims, config))
        self.assertTrue(verify_dag_parent_commit(generic, config, context))
        self.assertTrue(verify_bardo_proof(bardo, config, context))

        gm = dag_parent_commit_metrics(generic, config)
        bm = bardo_proof_metrics(bardo, config)
        self.assertEqual(gm, bm)

    def test_parent_commitment_mutation_rejects(self):
        config = Grid2DConfig(width=5, height=5, memory_decay=0.0)
        model = Grid2D("A" * 25, config=config)
        before1 = model.state_string()
        pulse = [0.0] * 25
        pulse[12] = 0.9
        model.step(pulse)
        before2 = model.state_string()
        model.step([0.0] * 25)
        after2 = model.state_string()
        claims = (TransitionClaim(1, 12, before2[12]), TransitionClaim(2, 12, after2[12]))
        context = VerificationContext(
            expected_queries=((1, 12), (2, 12)),
            state_roots=((0, state_root(before1)), (1, state_root(before2))),
            expected_stimuli=((1, 12, 0.9), (2, 12, 0.0)),
        )
        facts = {}
        for tick, state in ((0, before1), (1, before2)):
            for site in (12, 7, 17, 11, 13):
                facts[(tick, site)] = committed_fact(state, tick, site)
        nodes = list(build_dag_nodes(claims, config))
        proof = DagParentCommitProof(tuple(facts[key] for key in sorted(facts)), context.expected_stimuli, tuple(nodes))
        self.assertTrue(verify_dag_parent_commit(proof, config, context))
        nodes[1] = type(nodes[1])(nodes[1].claim, "sha256:" + "0" * 64)
        self.assertFalse(verify_dag_parent_commit(DagParentCommitProof(proof.phase_facts, proof.stimulus_facts, tuple(nodes)), config, context))


if __name__ == "__main__":
    unittest.main()
