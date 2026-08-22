import unittest

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.transition_edges import ConventionalEdgeObserverGrid2D
from morphos.witness import WitnessLaw
from morphos.witness_multierasure import MultiErasureAuthorityGrid2D


class TransitionEdgeControlTests(unittest.TestCase):
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

    def test_observer_does_not_change_w85_outcome(self):
        target, source, baseline = self._case(MultiErasureAuthorityGrid2D)
        _, _, observed = self._case(ConventionalEdgeObserverGrid2D)
        _corrupt_all(baseline, source)
        _corrupt_all(observed, source)

        baseline.run([0.0] * 8)
        observed.run([0.0] * 8)

        self.assertEqual(baseline.state_string(), target)
        self.assertEqual(observed.state_string(), baseline.state_string())
        self.assertEqual(
            observed.multi_erasure_decode_events,
            baseline.multi_erasure_decode_events,
        )
        self.assertEqual(observed.protected_targets, baseline.protected_targets)

    def test_every_record_is_a_real_phase_change(self):
        _, source, observed = self._case(ConventionalEdgeObserverGrid2D)
        initial = observed.state_string()
        _corrupt_all(observed, source)
        post_corruption = observed.state_string()
        self.assertNotEqual(initial, post_corruption)

        observed.run([0.0] * 8)
        self.assertGreater(len(observed.transition_records), 0)
        for record in observed.transition_records:
            self.assertNotEqual(record.from_phase, record.to_phase)
            self.assertIn(record.from_phase, {"A", "M", "C"})
            self.assertIn(record.to_phase, {"A", "M", "C"})

    def test_transition_replay_reconstructs_exact_final_state(self):
        _, source, observed = self._case(ConventionalEdgeObserverGrid2D)
        _corrupt_all(observed, source)
        replay_initial = observed.state_string()
        observed.run([0.0] * 8)
        self.assertEqual(observed.replay(replay_initial), observed.state_string())

    def test_canonical_transition_ids_are_deterministic(self):
        _, source, first = self._case(ConventionalEdgeObserverGrid2D)
        _, _, second = self._case(ConventionalEdgeObserverGrid2D)
        _corrupt_all(first, source)
        _corrupt_all(second, source)
        first.run([0.0] * 8)
        second.run([0.0] * 8)

        self.assertEqual(
            [record.transition_id for record in first.transition_records],
            [record.transition_id for record in second.transition_records],
        )
        self.assertEqual(
            first.transition_metadata_bytes(),
            second.transition_metadata_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
