from __future__ import annotations

import unittest

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalLaw
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw
from morphos.witness import WitnessLaw
from morphos.witness_persistent import PersistentWitnessGrid2D


class PersistentWitnessTests(unittest.TestCase):
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

    def model(self, drive: float = 0.25) -> PersistentWitnessGrid2D:
        return PersistentWitnessGrid2D(
            "C" * 25,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
            witness_law=WitnessLaw(witness_drive=drive, commit_delay=8),
        )

    @staticmethod
    def corrupt_all_copy_planes(model, index: int) -> None:
        model.perturb_primary([index])
        model.perturb_local_mirror([index])
        model.perturb_domain_mirror([index])
        model.perturb_system_mirror([index])

    def test_intent_is_latched_before_binary_syndrome_disappears(self) -> None:
        model = self.model()
        self.corrupt_all_copy_planes(model, 12)
        self.assertEqual(model.localized_error_index(), 12)
        model.step(0.0)
        self.assertEqual(model.latched_index, 12)
        self.assertEqual(model.latched_target, "C")
        self.assertGreater(model.latch_events, 0)

    def test_latched_intent_survives_mixed_phase_and_completes_recovery(self) -> None:
        model = self.model()
        self.corrupt_all_copy_planes(model, 12)
        model.step(0.0)
        # MORPHOS moves at most one adjacent phase per tick; W2 must keep the
        # intent if the first corrective step enters M.
        if model.states[12] == "M":
            self.assertEqual(model.latched_target, "C")
        for _ in range(5):
            model.step(0.0)
        self.assertEqual(model.states[12], "C")
        self.assertIsNone(model.latched_index)
        self.assertGreater(model.latch_clear_events, 0)

    def test_corrupted_witness_cannot_create_initial_latch(self) -> None:
        model = self.model()
        self.corrupt_all_copy_planes(model, 12)
        model.perturb_witness_for_cell(12)
        self.assertEqual(model.syndrome(), ((), ()))
        model._maybe_latch_from_syndrome()
        self.assertIsNone(model.latched_index)

    def test_zero_drive_matches_m2_for_common_mode_fault(self) -> None:
        target = "C" * 25
        m2 = MultiReflectiveGrid2D(
            target,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
        )
        w2 = self.model(drive=0.0)
        for model in (m2, w2):
            self.corrupt_all_copy_planes(model, 12)
        for _ in range(6):
            m2.step(0.0)
            w2.step(0.0)
        self.assertEqual(w2.state_string(), m2.state_string())
        self.assertEqual(w2.local_mirror_string(), m2.local_mirror_string())
        self.assertEqual(w2.domain_mirror_string(), m2.domain_mirror_string())
        self.assertEqual(w2.system_mirror_string(), m2.system_mirror_string())


if __name__ == "__main__":
    unittest.main()
