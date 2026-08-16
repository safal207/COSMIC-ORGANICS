import unittest

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import _fixed_binary_targets, _m2_law, _s2_components, _sha_binary_seeds
from morphos.witness import WitnessLaw
from morphos.witness_handoff import HandoffAuthorityGrid2D


class HandoffAuthorityTests(unittest.TestCase):
    def _locked_case(self):
        base = _manifest()
        config, hierarchy = _s2_components(base, 9, 9)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(202608161023, 64, 81), config, hierarchy, 6
        )[:8]
        # Diagnostic target 1 / source 3 is a W4 collateral-migration failure:
        # source 3 repairs, parity then uniquely points at neighbouring cell 2.
        target = targets[1]
        model = HandoffAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        return target, model

    def test_handoff_moves_ownership_only_after_source_reaches_target(self):
        target, model = self._locked_case()
        _corrupt_all(model, 3)
        model.step(0.0)
        self.assertEqual(model.latched_index, 3)
        model.step(0.0)
        self.assertEqual(model.states[3], target[3])
        self.assertEqual(model.latched_index, 3)
        model.step(0.0)
        self.assertGreaterEqual(model.handoff_events, 1)
        self.assertEqual(model.handoff_history[0], (3, 2))
        self.assertEqual(model.latched_index, 2)

    def test_previous_owner_remains_protected_after_handoff(self):
        target, model = self._locked_case()
        _corrupt_all(model, 3)
        model.run([0.0] * 3)
        self.assertIn(3, model.protected_targets)
        self.assertEqual(model.protected_targets[3], target[3])
        self.assertIn(2, model.protected_targets)

    def test_explicit_external_stimulus_cancels_repair_chain(self):
        _, model = self._locked_case()
        _corrupt_all(model, 3)
        model.run([0.0] * 3)
        self.assertTrue(model.protected_targets)
        model.step(2.0)
        self.assertFalse(model.selective_fence_active)
        self.assertEqual(model.protected_targets, {})


if __name__ == "__main__":
    unittest.main()
