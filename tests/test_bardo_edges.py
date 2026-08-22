import unittest

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.bardo_edges import BardoEdgeFieldObserverGrid2D, BardoRelation
from morphos.transition_edges import ConventionalEdgeObserverGrid2D
from morphos.witness import WitnessLaw
from morphos.witness_multierasure import MultiErasureAuthorityGrid2D


class BardoEdgeCandidateTests(unittest.TestCase):
    def _case(self, cls):
        base = _manifest()
        config, hierarchy = _s2_components(base, 7, 7)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(202608167012, 64, 49), config, hierarchy, 6
        )[:8]
        target = targets[3]
        source = _noise_indices(202608167012, 3, 49, 6)[5]
        self.assertEqual(source, 19)
        model = cls(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        return target, source, model

    def test_candidate_is_observational_only(self):
        target, source, baseline = self._case(MultiErasureAuthorityGrid2D)
        _, _, candidate = self._case(BardoEdgeFieldObserverGrid2D)
        _corrupt_all(baseline, source)
        _corrupt_all(candidate, source)
        baseline.run([0.0] * 8)
        candidate.run([0.0] * 8)

        self.assertEqual(baseline.state_string(), target)
        self.assertEqual(candidate.state_string(), baseline.state_string())
        self.assertEqual(candidate.protected_targets, baseline.protected_targets)
        self.assertEqual(
            candidate.multi_erasure_decode_events,
            baseline.multi_erasure_decode_events,
        )

    def test_candidate_semantics_match_conventional_control(self):
        _, source, conventional = self._case(ConventionalEdgeObserverGrid2D)
        _, _, candidate = self._case(BardoEdgeFieldObserverGrid2D)
        _corrupt_all(conventional, source)
        _corrupt_all(candidate, source)
        conventional.run([0.0] * 12)
        candidate.run([0.0] * 12)

        conventional_records = conventional.transition_records
        candidate_records = candidate.transition_records
        self.assertEqual(conventional_records, candidate_records)
        self.assertEqual(
            [record.transition_id for record in conventional_records],
            [record.transition_id for record in candidate_records],
        )
        self.assertEqual(
            conventional.transition_metadata_bytes(),
            candidate.transition_metadata_bytes(),
        )

    def test_candidate_replay_is_exact(self):
        _, source, candidate = self._case(BardoEdgeFieldObserverGrid2D)
        _corrupt_all(candidate, source)
        replay_initial = candidate.state_string()
        candidate.run([0.0] * 12)
        self.assertEqual(candidate.replay(replay_initial), candidate.state_string())

    def test_relation_field_indexes_occurrences(self):
        _, source, candidate = self._case(BardoEdgeFieldObserverGrid2D)
        _corrupt_all(candidate, source)
        candidate.run([0.0] * 12)
        first = candidate.transition_records[0]
        relation = BardoRelation.from_record(first)
        self.assertIn(first, candidate.occurrences(relation))
        self.assertEqual(candidate.record_by_id(first.transition_id), first)


if __name__ == "__main__":
    unittest.main()
