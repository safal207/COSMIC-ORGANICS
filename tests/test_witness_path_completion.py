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
from morphos.witness_path_completion import PathCompletionAuthorityGrid2D


class PathCompletionAuthorityTests(unittest.TestCase):
    def _locked_failed_case(self):
        base = _manifest()
        config, hierarchy = _s2_components(base, 7, 7)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(202608164011, 64, 49), config, hierarchy, 6
        )[:8]
        target = targets[3]
        source = _noise_indices(202608164011, 3, 49, 6)[1]
        self.assertEqual(source, 20)
        model = PathCompletionAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        return target, source, model

    def test_locked_w8_v0_failure_completes_through_m(self):
        target, source, model = self._locked_failed_case()
        _corrupt_all(model, source)
        model.run([0.0] * 12)
        self.assertEqual(model.states[source], target[source])
        self.assertEqual(model.state_string(), target)
        self.assertGreaterEqual(model.path_completion_binary_events, 1)
        self.assertGreaterEqual(model.path_completion_m_events, 1)

    def test_path_completion_stops_when_repair_set_expands(self):
        base = _manifest()
        config, hierarchy = _s2_components(base, 5, 5)
        target = _fixed_binary_targets(
            _sha_binary_seeds(202608163001, 64, 25), config, hierarchy, 6
        )[:8][0]
        source = _noise_indices(202608163001, 0, 25, 6)[1]
        model = PathCompletionAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        _corrupt_all(model, source)
        for _ in range(8):
            model.step(0.0)
            if len(model.protected_targets) > 1:
                frozen = model.margin_completion_events
                model.step(0.0)
                self.assertEqual(model.margin_completion_events, frozen)
                return
        self.fail("locked W7 case never entered a multi-target repair set")

    def test_external_intent_has_no_path_completion_authority(self):
        base = _manifest()
        config, hierarchy = _s2_components(base, 5, 5)
        model = PathCompletionAuthorityGrid2D(
            "A" * 25,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        model.run([2.0] * 18)
        self.assertEqual(model.margin_completion_events, 0)
        self.assertEqual(model.path_completion_m_events, 0)
        self.assertEqual(model.state_string(), "C" * 25)

    def test_zero_witness_cannot_activate_path_completion(self):
        target, source, model = self._locked_failed_case()
        base = _manifest()
        config, hierarchy = _s2_components(base, 7, 7)
        model = PathCompletionAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.0, commit_delay=8),
        )
        _corrupt_all(model, source)
        model.run([0.0] * 12)
        self.assertEqual(model.margin_completion_events, 0)
        self.assertEqual(model.path_completion_m_events, 0)


if __name__ == "__main__":
    unittest.main()
