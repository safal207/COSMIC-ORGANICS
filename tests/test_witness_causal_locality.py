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
    def _fresh_cancelled_case(self, drive=0.25):
        base = _manifest()
        config, hierarchy = _s2_components(base, 9, 9)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(202608166023, 64, 81), config, hierarchy, 6
        )[:8]
        target = targets[6]
        source = _noise_indices(202608166023, 6, 81, 6)[5]
        self.assertEqual(source, 51)
        model = CausalLocalityAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=drive, commit_delay=8),
        )
        return target, source, model

    def test_locality_decoder_adds_cancelled_horizontal_pair(self):
        target, source, model = self._fresh_cancelled_case()
        _corrupt_all(model, source)
        model.step(0.0)
        self.assertEqual(model.states[source], "M")
        model.step(0.0)
        self.assertEqual(model.states[source], target[source])
        self.assertEqual(model.syndrome(), ((), (5, 7)))
        self.assertEqual(model.locality_pair_decode_events, 0)
        model.step(0.0)
        self.assertEqual(model.locality_pair_decode_events, 1)
        self.assertEqual(model.last_locality_pair, (50, 52))
        self.assertEqual(model.last_locality_kind, "same_row_cancelled")
        self.assertEqual(set(model.protected_targets), {50, 51, 52})

    def test_known_cancelled_case_recovers_exactly(self):
        target, source, model = self._fresh_cancelled_case()
        _corrupt_all(model, source)
        model.run([0.0] * 12)
        self.assertEqual(model.state_string(), target)
        self.assertEqual(model.locality_pair_decode_events, 1)

    def test_non_neighbor_cancelled_axis_fails_closed(self):
        target, source, model = self._fresh_cancelled_case()
        # Establish a verified one-source repair transaction without corruption.
        model.selective_fence_active = True
        model.latched_index = source
        model.latched_target = target[source]
        model.protected_targets = {source: target[source]}
        model.states[source] = target[source]

        # Two same-row flips produce row-parity cancellation, but both are too
        # far from source 51 to satisfy the causal-locality authority boundary.
        far_pair = (48, 53)
        for index in far_pair:
            model.states[index] = "C" if target[index] == "A" else "A"
        self.assertEqual(model.syndrome()[0], ())
        self.assertEqual(len(model.syndrome()[1]), 2)
        self.assertIsNone(model._cancelled_axis_candidate(source))
        self.assertFalse(model._locality_pair_decode())
        self.assertEqual(model.locality_pair_decode_events, 0)

    def test_source_must_be_verified_before_locality_decode(self):
        _, source, model = self._fresh_cancelled_case()
        _corrupt_all(model, source)
        model.step(0.0)
        self.assertEqual(model.states[source], "M")
        self.assertFalse(model._locality_pair_decode())
        self.assertEqual(model.locality_pair_decode_events, 0)

    def test_zero_witness_cannot_activate_locality_decode(self):
        _, source, model = self._fresh_cancelled_case(drive=0.0)
        _corrupt_all(model, source)
        model.run([0.0] * 12)
        self.assertEqual(model.locality_pair_decode_events, 0)
        self.assertEqual(model.locality_pair_added_targets, 0)


if __name__ == "__main__":
    unittest.main()
