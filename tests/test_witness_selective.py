from __future__ import annotations

import unittest

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalLaw
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw
from morphos.witness import WitnessLaw
from morphos.witness_selective import SelectiveAuthorityGrid2D


class SelectiveAuthorityTests(unittest.TestCase):
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
        return SelectiveAuthorityGrid2D(
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

    def test_common_mode_fault_suppresses_only_conflicting_target_mirrors(self) -> None:
        model = self.model()
        self.corrupt_all_copy_planes(model, 12)
        model.step(0.0)
        self.assertTrue(model.selective_fence_active)
        self.assertGreater(model.suppressed_mirror_contributions, 0)
        # Only three target-cell mirror claims are contradictory on the first tick.
        self.assertEqual(model.suppressed_mirror_contributions, 3)

    def test_primary_only_fault_preserves_healthy_target_mirror_authority(self) -> None:
        model = self.model()
        model.perturb_primary([12])
        model.step(0.0)
        self.assertTrue(model.selective_fence_active)
        self.assertEqual(model.suppressed_mirror_contributions, 0)
        self.assertEqual(model.preserved_mirror_contributions, 3)

    def test_selective_fence_releases_after_target_mirrors_recommit(self) -> None:
        model = self.model()
        self.corrupt_all_copy_planes(model, 12)
        for _ in range(8):
            model.step(0.0)
        self.assertFalse(model.selective_fence_active)
        self.assertEqual(model.states[12], "C")
        self.assertEqual(model.local_mirror_states[12], "C")
        self.assertEqual(model.domain_mirror_states[12], "C")
        self.assertEqual(model.system_mirror_states[12], "C")
        self.assertGreater(model.fence_release_events, 0)

    def test_corrupted_witness_does_not_open_selective_fence(self) -> None:
        model = self.model()
        self.corrupt_all_copy_planes(model, 12)
        model.perturb_witness_for_cell(12)
        model.step(0.0)
        self.assertFalse(model.selective_fence_active)
        self.assertEqual(model.fence_open_events, 0)

    def test_zero_drive_matches_m2_common_mode(self) -> None:
        target = "C" * 25
        m2 = MultiReflectiveGrid2D(
            target,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
        )
        w4 = self.model(drive=0.0)
        for model in (m2, w4):
            self.corrupt_all_copy_planes(model, 12)
        for _ in range(8):
            m2.step(0.0)
            w4.step(0.0)
        self.assertEqual(w4.state_string(), m2.state_string())
        self.assertEqual(w4.local_mirror_string(), m2.local_mirror_string())
        self.assertEqual(w4.domain_mirror_string(), m2.domain_mirror_string())
        self.assertEqual(w4.system_mirror_string(), m2.system_mirror_string())

    def test_persistent_external_stimulus_remains_learnable(self) -> None:
        model = self.model(initial="A" * 25)
        initial_witness = model.witness_signature()
        for _ in range(18):
            model.step(2.0)
        for _ in range(16):
            model.step(0.0)
        expected = "C" * 25
        self.assertEqual(model.state_string(), expected)
        self.assertEqual(model.local_mirror_string(), expected)
        self.assertEqual(model.domain_mirror_string(), expected)
        self.assertEqual(model.system_mirror_string(), expected)
        self.assertNotEqual(model.witness_signature(), initial_witness)


if __name__ == "__main__":
    unittest.main()
