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
from morphos.witness_causal_locality import CausalLocalityAuthorityGrid2D


class CausalLocalityAuthorityTests(unittest.TestCase):
    def _fresh_miss_case(self, drive=0.25):
        base = _manifest()
        config, hierarchy = _s2_components(base, 9, 9)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(202608166023, 64, 81), config, hierarchy, 6
        )[:8]
        target = targets[6]
        source = _noise_indices(202608166023, 6, 81, 6)[5]
        model = CausalLocalityAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=drive, commit_delay=8),
        )
        return target, source, model

    def test_locality_pair_repairs_the_frozen_same_row_residual(self):
        target, source, model = self._fresh_miss_case()
        self.assertEqual(source, 51)
        _corrupt_all(model, source)

        model.step(0.0)
        self.assertEqual(model.states[source], "M")
        self.assertEqual(model.locality_pair_decode_events, 0)

        model.step(0.0)
        self.assertEqual(model.states[source], target[source])
        self.assertEqual(model.locality_pair_decode_events, 0)

        model.step(0.0)
        self.assertEqual(model.locality_pair_decode_events, 1)
        self.assertEqual(model.last_locality_pair, (50, 52))
        self.assertEqual(set(model.protected_targets), {50, 51, 52})

        model.run([0.0] * 5)
        self.assertEqual(model.state_string(), target)

    def test_locality_decode_requires_verified_source(self):
        _, source, model = self._fresh_miss_case()
        _corrupt_all(model, source)
        model.step(0.0)
        self.assertEqual(model.states[source], "M")
        self.assertFalse(model._locality_pair_decode())
        self.assertEqual(model.locality_pair_decode_events, 0)

    def test_non_neighbour_same_axis_pair_fails_closed(self):
        target, source, model = self._fresh_miss_case()
        _corrupt_all(model, source)
        model.step(0.0)
        model.step(0.0)
        self.assertEqual(model.states[source], target[source])

        # Remove the observed immediate-neighbour residual, then create another
        # same-row parity cancellation that is not adjacent to the source.
        model.states[50] = target[50]
        model.states[52] = target[52]
        for index in (47, 49):
            model.states[index] = model._opposite(target[index])

        self.assertEqual(model.syndrome(), ((), (2, 4)))
        self.assertIsNone(model._cancelled_axis_pair())
        self.assertFalse(model._locality_pair_decode())
        self.assertEqual(model.locality_pair_decode_events, 0)

    def test_symmetric_same_column_case_is_supported(self):
        base = _manifest()
        config, hierarchy = _s2_components(base, 5, 5)
        source = 12  # row 2, column 2
        model = CausalLocalityAuthorityGrid2D(
            "A" * 25,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        model.selective_fence_active = True
        model.latched_index = source
        model.latched_target = "A"
        model.protected_targets = {source: "A"}
        model.states[7] = "C"   # above
        model.states[17] = "C"  # below

        self.assertEqual(model.syndrome(), ((1, 3), ()))
        self.assertTrue(model._locality_pair_decode())
        self.assertEqual(model.last_locality_pair, (7, 17))
        self.assertEqual(set(model.protected_targets), {7, 12, 17})

    def test_zero_witness_cannot_activate_locality_decode(self):
        _, source, model = self._fresh_miss_case(drive=0.0)
        _corrupt_all(model, source)
        model.run([0.0] * 12)
        self.assertEqual(model.locality_pair_decode_events, 0)
        self.assertEqual(model.locality_pair_added_targets, 0)


if __name__ == "__main__":
    unittest.main()
