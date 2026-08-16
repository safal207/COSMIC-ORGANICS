from __future__ import annotations

import unittest

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalLaw
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw
from morphos.witness import IndependentWitnessGrid2D, WitnessLaw


class IndependentWitnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Grid2DConfig(
            width=5,
            height=5,
            memory_decay=0.0,
            anchor_threshold=0.5,
            adaptive_threshold=0.35,
            anchor_coupling=0.75,
            adaptive_coupling=0.5,
            mixed_relax_threshold=0.05,
            mask="checkerboard",
            neighborhood="von_neumann",
        )
        self.hierarchy = HierarchicalLaw(
            reference_linear_size=5.0,
            exponent=0.06,
            domain_size=3,
        )
        self.m2_law = MultiReflectiveLaw(
            local_coupling=0.15,
            domain_coupling=0.08,
            system_coupling=0.08,
            local_commit_delay=3,
            domain_commit_delay=4,
            system_commit_delay=5,
        )

    def model(self, *, drive: float = 0.75) -> IndependentWitnessGrid2D:
        return IndependentWitnessGrid2D(
            "C" * 25,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
            witness_law=WitnessLaw(witness_drive=drive, commit_delay=8),
        )

    def test_single_bit_syndrome_localizes_error(self) -> None:
        model = self.model()
        model.perturb_primary([12])
        self.assertEqual(model.localized_error_index(), 12)
        self.assertEqual(model.syndrome(), ((2,), (2,)))

    def test_corrupting_witness_with_same_bit_erases_privileged_signal(self) -> None:
        model = self.model()
        for perturb in (
            model.perturb_primary,
            model.perturb_local_mirror,
            model.perturb_domain_mirror,
            model.perturb_system_mirror,
        ):
            perturb([12])
        model.perturb_witness_for_cell(12)
        self.assertEqual(model.syndrome(), ((), ()))
        self.assertIsNone(model.localized_error_index())

    def test_zero_witness_drive_matches_m2_when_planes_are_identical(self) -> None:
        target = "C" * 25
        m2 = MultiReflectiveGrid2D(
            target,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
        )
        w1 = IndependentWitnessGrid2D(
            target,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
            witness_law=WitnessLaw(witness_drive=0.0, commit_delay=8),
        )
        for model in (m2, w1):
            model.perturb_primary([12])
            model.perturb_local_mirror([12])
            model.perturb_domain_mirror([12])
            model.perturb_system_mirror([12])
        for _ in range(6):
            m2.step(0.0)
            w1.step(0.0)
        self.assertEqual(w1.state_string(), m2.state_string())
        self.assertEqual(w1.local_mirror_string(), m2.local_mirror_string())
        self.assertEqual(w1.domain_mirror_string(), m2.domain_mirror_string())
        self.assertEqual(w1.system_mirror_string(), m2.system_mirror_string())

    def test_witness_is_compact_non_copy_representation(self) -> None:
        model = self.model()
        rows, columns = model.witness_signature()
        self.assertEqual(len(rows), self.config.height)
        self.assertEqual(len(columns), self.config.width)
        self.assertLess(len(rows) + len(columns), len(model.states))

    def test_persistent_strong_signal_can_recommit_witness(self) -> None:
        model = IndependentWitnessGrid2D(
            "A" * 25,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
            witness_law=WitnessLaw(witness_drive=0.75, commit_delay=8),
        )
        initial_signature = model.witness_signature()
        for _ in range(16):
            model.step(2.0)
        for _ in range(20):
            model.step(0.0)
        self.assertEqual(model.state_string(), "C" * 25)
        self.assertEqual(model.local_mirror_string(), "C" * 25)
        self.assertEqual(model.domain_mirror_string(), "C" * 25)
        self.assertEqual(model.system_mirror_string(), "C" * 25)
        self.assertNotEqual(model.witness_signature(), initial_signature)
        self.assertGreater(model.witness_commit_events, 0)


if __name__ == "__main__":
    unittest.main()
