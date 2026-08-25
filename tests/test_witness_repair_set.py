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
from morphos.witness_repair_set import RepairSetAuthorityGrid2D


class RepairSetAuthorityTests(unittest.TestCase):
    def _locked_case(self):
        base = _manifest()
        config, hierarchy = _s2_components(base, 5, 5)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(202608163001, 64, 25), config, hierarchy, 6
        )[:8]
        target = targets[0]
        source = _noise_indices(202608163001, 0, 25, 6)[1]
        self.assertEqual(source, 19)
        model = RepairSetAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        return target, source, model

    def test_erasure_handoff_adds_responsibility_instead_of_replacing_it(self):
        target, source, model = self._locked_case()
        _corrupt_all(model, source)
        model.run([0.0] * 3)
        self.assertGreaterEqual(model.erasure_handoff_events, 1)
        self.assertEqual(len(model.protected_targets), 2)
        self.assertIn(source, model.protected_targets)
        self.assertIn(model.latched_index, model.protected_targets)

    def test_repair_set_applies_same_bounded_drive_to_every_touched_target(self):
        target, source, model = self._locked_case()
        _corrupt_all(model, source)
        model.run([0.0] * 3)
        stimuli = [0.0] * len(model.states)
        protected = dict(model.protected_targets)
        model._apply_latched_drive(stimuli)
        self.assertEqual(len(protected), 2)
        for index, endpoint in protected.items():
            expected = 0.25 if endpoint == "C" else -0.25
            self.assertAlmostEqual(stimuli[index], expected)
        self.assertEqual(
            sum(abs(value) > 1e-12 for value in stimuli), len(protected)
        )

    def test_explicit_external_stimulus_cancels_quiescent_repair_set(self):
        _, source, model = self._locked_case()
        _corrupt_all(model, source)
        model.run([0.0] * 3)
        self.assertTrue(model.protected_targets)
        model.step(2.0)
        self.assertFalse(model.selective_fence_active)
        self.assertEqual(model.protected_targets, {})


if __name__ == "__main__":
    unittest.main()
