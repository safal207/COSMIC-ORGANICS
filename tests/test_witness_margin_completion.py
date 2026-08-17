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
from morphos.witness_margin_completion import MarginCompletionAuthorityGrid2D
from morphos.witness_repair_set import RepairSetAuthorityGrid2D


class MarginCompletionAuthorityTests(unittest.TestCase):
    def _case(self, width: int, seed: int, target_index: int, trial_index: int):
        base = _manifest()
        config, hierarchy = _s2_components(base, width, width)
        cells = width * width
        targets = _fixed_binary_targets(
            _sha_binary_seeds(seed, 64 if width < 9 else 48, cells),
            config,
            hierarchy,
            6,
        )[:8]
        target = targets[target_index]
        source = _noise_indices(seed, target_index, cells, 6)[trial_index]
        kwargs = dict(
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        return target, source, kwargs

    def test_locked_negative_margin_source_gets_entry_completion(self):
        # Frozen W7-confirmation residual from PR #31/R2.
        target, source, kwargs = self._case(7, 202608164011, 0, 5)
        self.assertEqual(source, 14)

        w7 = RepairSetAuthorityGrid2D(target, **kwargs)
        w8 = MarginCompletionAuthorityGrid2D(target, **kwargs)
        _corrupt_all(w7, source)
        _corrupt_all(w8, source)
        w7.run([0.0] * 12)
        w8.run([0.0] * 12)

        self.assertNotEqual(w7.state_string(), target)
        self.assertGreaterEqual(w8.margin_completion_events, 1)
        self.assertEqual(w8.states[source], target[source])

    def test_no_witness_drive_means_no_completion_authority(self):
        target, source, kwargs = self._case(7, 202608164011, 0, 5)
        kwargs["witness_law"] = WitnessLaw(witness_drive=0.0, commit_delay=8)
        model = MarginCompletionAuthorityGrid2D(target, **kwargs)
        _corrupt_all(model, source)
        model.run([0.0] * 8)
        self.assertEqual(model.margin_completion_events, 0)
        self.assertFalse(model.selective_fence_active)

    def test_external_intent_never_uses_margin_completion(self):
        base = _manifest()
        config, hierarchy = _s2_components(base, 5, 5)
        model = MarginCompletionAuthorityGrid2D(
            "A" * 25,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        model.run([2.0] * 18)
        self.assertEqual(model.margin_completion_events, 0)
        self.assertEqual(model.state_string(), "C" * 25)

    def test_completion_is_entry_only_not_post_handoff(self):
        # A known W7 ping-pong-rescue family case reaches a multi-target repair set.
        base = _manifest()
        config, hierarchy = _s2_components(base, 5, 5)
        target = _fixed_binary_targets(
            _sha_binary_seeds(202608163001, 64, 25), config, hierarchy, 6
        )[:8][0]
        source = _noise_indices(202608163001, 0, 25, 6)[1]
        model = MarginCompletionAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        _corrupt_all(model, source)
        for _ in range(8):
            before = model.margin_completion_events
            model.step(0.0)
            if len(model.protected_targets) > 1:
                # Once ownership expands, W8 must not add new completion events.
                frozen = model.margin_completion_events
                model.step(0.0)
                self.assertEqual(model.margin_completion_events, frozen)
                break
        else:
            self.fail("locked W7 case never entered a multi-target repair set")


if __name__ == "__main__":
    unittest.main()
