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
from morphos.witness_erasure import ErasureAwareAuthorityGrid2D
from morphos.witness_handoff import HandoffAuthorityGrid2D


class ErasureAwareWitnessTests(unittest.TestCase):
    def _model(self, initial: str, size: int = 5):
        base = _manifest()
        config, hierarchy = _s2_components(base, size, size)
        return ErasureAwareAuthorityGrid2D(
            initial,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )

    def test_single_m_erasure_is_inferred_from_independent_row_and_column_parity(self):
        state = list("A" * 25)
        state[7] = "C"
        model = self._model("".join(state))
        model.states[7] = "M"
        self.assertEqual(model.erasure_aware_localization(), (7, "C"))

    def test_extra_binary_error_makes_single_erasure_fail_closed(self):
        model = self._model("A" * 25)
        model.states[7] = "M"
        model.states[8] = "C"
        self.assertIsNone(model.erasure_aware_localization())

    def test_multiple_m_states_fail_closed(self):
        model = self._model("A" * 25)
        model.states[7] = "M"
        model.states[8] = "M"
        self.assertIsNone(model.erasure_aware_localization())

    def test_locked_mixed_blind_case_can_handoff_without_retuning(self):
        base = _manifest()
        config, hierarchy = _s2_components(base, 5, 5)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(202608163001, 64, 25), config, hierarchy, 6
        )[:8]
        target = targets[0]
        indices = _noise_indices(202608163001, 0, 25, 6)
        source = indices[1]
        self.assertEqual(source, 19)

        common = dict(
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
        )
        w5 = HandoffAuthorityGrid2D(target, **common)
        w6 = ErasureAwareAuthorityGrid2D(target, **common)
        _corrupt_all(w5, source)
        _corrupt_all(w6, source)
        w5.run([0.0] * 8)
        w6.run([0.0] * 8)

        residual = [
            index
            for index, (actual, expected) in enumerate(zip(w5.states, target))
            if actual != expected
        ]
        self.assertEqual(len(residual), 1)
        self.assertEqual(w5.states[residual[0]], "M")
        self.assertEqual(w5.handoff_events, 0)
        self.assertGreaterEqual(w6.erasure_handoff_events, 1)
        self.assertTrue(
            any(new_owner == residual[0] for _, new_owner in w6.handoff_history)
        )


if __name__ == "__main__":
    unittest.main()
