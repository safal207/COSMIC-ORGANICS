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
from morphos.witness_multierasure import MultiErasureAuthorityGrid2D


class MultiErasureAuthorityTests(unittest.TestCase):
    def _persistent_case(self, drive=0.25):
        base = _manifest()
        config, hierarchy = _s2_components(base, 7, 7)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(202608167012, 64, 49), config, hierarchy, 6
        )[:8]
        target = targets[3]
        source = _noise_indices(202608167012, 3, 49, 6)[5]
        self.assertEqual(source, 19)
        model = MultiErasureAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=drive, commit_delay=8),
        )
        return target, source, model

    def test_known_persistent_case_decodes_two_M_endpoints(self):
        target, source, model = self._persistent_case()
        _corrupt_all(model, source)
        # The two-M state exists after tick 3; ownership is evaluated at the
        # beginning of tick 4, matching the runtime step contract.
        model.run([0.0] * 4)
        self.assertEqual(model.states[source], target[source])
        self.assertEqual(model.multi_erasure_decode_events, 1)
        self.assertEqual(model.last_multi_erasure_indices, (20, 33))
        self.assertEqual(model.last_multi_erasure_targets, ("A", "A"))
        self.assertEqual(set(model.protected_targets), {19, 20, 33})

    def test_known_persistent_case_recovers_by_tick_8(self):
        target, source, model = self._persistent_case()
        _corrupt_all(model, source)
        model.run([0.0] * 8)
        self.assertEqual(model.state_string(), target)
        self.assertGreaterEqual(model.multi_erasure_decode_events, 1)

    def test_more_than_two_M_fails_closed(self):
        target, source, model = self._persistent_case()
        _corrupt_all(model, source)
        # Inspect the post-tick-3 state before the next step can invoke W8.5.
        model.run([0.0] * 3)
        self.assertEqual(model.states[source], target[source])
        m_indices = [i for i, phase in enumerate(model.states) if phase == "M"]
        self.assertEqual(len(m_indices), 2)
        extra = next(
            i
            for i, phase in enumerate(model.states)
            if i not in m_indices and i != source and phase in ("A", "C")
        )
        model.states[extra] = "M"
        self.assertFalse(model._multi_erasure_decode())
        self.assertEqual(model.multi_erasure_decode_events, 0)

    def test_unverified_source_fails_closed(self):
        _, source, model = self._persistent_case()
        _corrupt_all(model, source)
        model.step(0.0)
        self.assertEqual(model.states[source], "M")
        self.assertFalse(model._multi_erasure_decode())
        self.assertEqual(model.multi_erasure_decode_events, 0)

    def test_zero_witness_cannot_activate_multi_erasure_decode(self):
        _, source, model = self._persistent_case(drive=0.0)
        _corrupt_all(model, source)
        model.run([0.0] * 12)
        self.assertEqual(model.multi_erasure_decode_events, 0)
        self.assertEqual(model.multi_erasure_added_targets, 0)


if __name__ == "__main__":
    unittest.main()
