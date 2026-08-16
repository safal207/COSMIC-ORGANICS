from __future__ import annotations

import unittest

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalLaw
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw
from morphos.witness import WitnessLaw
from morphos.witness_fence import RecoveryFenceGrid2D


class RecoveryFenceTests(unittest.TestCase):
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

    def model(self, initial: str = "C" * 25, drive: float = 0.25):
        return RecoveryFenceGrid2D(
            initial,
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

    def test_common_mode_fault_opens_fence(self) -> None:
        model = self.model()
        self.corrupt_all_copy_planes(model, 12)
        model.step(0.0)
        self.assertTrue(model.recovery_fence_active)
        self.assertEqual(model.latched_index, 12)
        self.assertEqual(model.fence_open_events, 1)

    def test_fence_remains_until_mirrors_recommit(self) -> None:
        model = self.model()
        self.corrupt_all_copy_planes(model, 12)
        model.step(0.0)
        model.step(0.0)
        self.assertEqual(model.states[12], "C")
        self.assertTrue(model.recovery_fence_active)
        self.assertNotEqual(model.local_mirror_states[12], model.states[12])

        for _ in range(6):
            model.step(0.0)
        self.assertFalse(model.recovery_fence_active)
        self.assertEqual(model.state_string(), "C" * 25)
        self.assertEqual(model.local_mirror_string(), model.state_string())
        self.assertEqual(model.domain_mirror_string(), model.state_string())
        self.assertEqual(model.system_mirror_string(), model.state_string())
        self.assertGreater(model.fence_release_events, 0)

    def test_corrupted_witness_does_not_open_fence(self) -> None:
        model = self.model()
        self.corrupt_all_copy_planes(model, 12)
        model.perturb_witness_for_cell(12)
        model.step(0.0)
        self.assertFalse(model.recovery_fence_active)
        self.assertEqual(model.fence_open_events, 0)

    def test_zero_drive_matches_m2_common_mode(self) -> None:
        target = "C" * 25
        m2 = MultiReflectiveGrid2D(
            target,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
        )
        w3 = self.model(drive=0.0)
        for model in (m2, w3):
            self.corrupt_all_copy_planes(model, 12)
        for _ in range(8):
            m2.step(0.0)
            w3.step(0.0)
        self.assertEqual(w3.state_string(), m2.state_string())
        self.assertEqual(w3.local_mirror_string(), m2.local_mirror_string())
        self.assertEqual(w3.domain_mirror_string(), m2.domain_mirror_string())
        self.assertEqual(w3.system_mirror_string(), m2.system_mirror_string())

    def test_persistent_external_stimulus_can_still_rewrite_witness(self) -> None:
        model = self.model(initial="A" * 25)
        initial_witness = model.witness_signature()
        for _ in range(18):
            model.step(2.0)
        for _ in range(16):
            model.step(0.0)
        self.assertEqual(model.state_string(), "C" * 25)
        self.assertEqual(model.local_mirror_string(), "C" * 25)
        self.assertEqual(model.domain_mirror_string(), "C" * 25)
        self.assertEqual(model.system_mirror_string(), "C" * 25)
        self.assertNotEqual(model.witness_signature(), initial_witness)
        self.assertGreater(model.witness_commit_events, 0)


if __name__ == "__main__":
    unittest.main()
