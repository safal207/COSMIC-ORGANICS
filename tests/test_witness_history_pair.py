import unittest

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.witness import WitnessLaw
from morphos.witness_history_pair import HistoryAwarePairAuthorityGrid2D


class HistoryAwarePairAuthorityTests(unittest.TestCase):
    def _case(self, trial_index=3, drive=0.25):
        base = _manifest()
        config, hierarchy = _s2_components(base, 9, 9)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(202608165022, 64, 81), config, hierarchy, 6
        )[:8]
        target = targets[5]
        source = _noise_indices(202608165022, 5, 81, 6)[trial_index]
        model = HistoryAwarePairAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=drive, commit_delay=8),
        )
        return target, source, model

    def test_history_pair_adds_the_two_frozen_residual_obligations(self):
        target, source, model = self._case(trial_index=3)
        self.assertEqual(source, 47)
        _corrupt_all(model, source)
        model.step(0.0)
        self.assertEqual(model.states[source], "M")
        self.assertEqual(model.history_pair_decode_events, 0)
        model.step(0.0)
        self.assertEqual(model.states[source], target[source])
        self.assertEqual(model.history_pair_decode_events, 0)
        model.step(0.0)
        self.assertEqual(model.history_pair_decode_events, 1)
        self.assertEqual(model.last_history_pair, (46, 56))
        self.assertEqual(set(model.protected_targets), {46, 47, 56})

    def test_virtual_parity_accepts_actual_pair_and_rejects_false_pair(self):
        target, source, model = self._case(trial_index=3)
        _corrupt_all(model, source)
        model.step(0.0)
        model.step(0.0)
        self.assertTrue(model._virtual_pair_restores_committed_parity((46, 56)))
        self.assertFalse(model._virtual_pair_restores_committed_parity((47, 55)))

    def test_history_decode_requires_source_verified_at_endpoint(self):
        _, source, model = self._case(trial_index=3)
        _corrupt_all(model, source)
        model.step(0.0)
        self.assertEqual(model.states[source], "M")
        self.assertFalse(model._history_pair_decode())
        self.assertEqual(model.history_pair_decode_events, 0)

    def test_zero_witness_cannot_activate_history_pair_decode(self):
        _, source, model = self._case(trial_index=3, drive=0.0)
        _corrupt_all(model, source)
        model.run([0.0] * 12)
        self.assertEqual(model.history_pair_decode_events, 0)
        self.assertEqual(model.history_pair_added_targets, 0)


if __name__ == "__main__":
    unittest.main()
