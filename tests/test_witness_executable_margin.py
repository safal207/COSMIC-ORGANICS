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
from morphos.witness_executable_margin import ExecutableMarginClosureGrid2D
from morphos.witness_path_completion import PathCompletionAuthorityGrid2D


class ExecutableMarginClosureTests(unittest.TestCase):
    def _sole_w81_residual(self, cls=ExecutableMarginClosureGrid2D, drive=0.25):
        base = _manifest()
        config, hierarchy = _s2_components(base, 7, 7)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(202608164012, 64, 49), config, hierarchy, 6
        )[:8]
        target = targets[3]
        source = _noise_indices(202608164012, 3, 49, 6)[1]
        self.assertEqual(source, 4)
        model = cls(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=drive, commit_delay=8),
        )
        return target, source, model

    def test_executable_closure_rescues_the_sole_w81_numeric_residual(self):
        target, source, old = self._sole_w81_residual(PathCompletionAuthorityGrid2D)
        _corrupt_all(old, source)
        old.run([0.0] * 12)
        self.assertNotEqual(old.state_string(), target)
        self.assertEqual(old.states[source], "M")

        target, source, model = self._sole_w81_residual()
        _corrupt_all(model, source)
        model.run([0.0] * 12)
        self.assertEqual(model.state_string(), target)
        self.assertEqual(model.states[source], target[source])
        self.assertGreaterEqual(model.executable_closure_events, 1)
        self.assertGreaterEqual(model.executable_closure_steps, 1)
        self.assertGreaterEqual(model.executable_closure_max_steps, 1)

    def test_zero_witness_has_no_executable_closure_authority(self):
        _, source, model = self._sole_w81_residual(drive=0.0)
        _corrupt_all(model, source)
        model.run([0.0] * 12)
        self.assertEqual(model.executable_closure_events, 0)
        self.assertEqual(model.executable_closure_steps, 0)

    def test_external_intent_has_no_executable_closure_authority(self):
        base = _manifest()
        config, hierarchy = _s2_components(base, 5, 5)
        model = ExecutableMarginClosureGrid2D(
            "A" * 25,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        model.run([2.0] * 18)
        self.assertEqual(model.state_string(), "C" * 25)
        self.assertEqual(model.executable_closure_events, 0)
        self.assertEqual(model.margin_completion_events, 0)

    def test_closure_is_not_available_after_repair_set_expands(self):
        base = _manifest()
        config, hierarchy = _s2_components(base, 5, 5)
        target = _fixed_binary_targets(
            _sha_binary_seeds(202608163001, 64, 25), config, hierarchy, 6
        )[:8][0]
        source = _noise_indices(202608163001, 0, 25, 6)[1]
        model = ExecutableMarginClosureGrid2D(
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
                frozen = model.executable_closure_events
                model.step(0.0)
                self.assertEqual(model.executable_closure_events, frozen)
                return
        self.fail("locked repair-set case never expanded beyond one target")


if __name__ == "__main__":
    unittest.main()
