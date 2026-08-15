from __future__ import annotations

import unittest

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalLaw
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw
from morphos.reflective import ReflectiveGrid2D, ReflectiveLaw


class MultiReflectiveTests(unittest.TestCase):
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

    def test_commit_delays_must_be_strictly_hierarchical(self) -> None:
        with self.assertRaises(ValueError):
            MultiReflectiveLaw(
                local_commit_delay=3,
                domain_commit_delay=3,
                system_commit_delay=5,
            )

    def test_disabling_higher_mirrors_matches_m1_primary_dynamics(self) -> None:
        initial = "CCCCCCCCCCCCCCCCCCCCCCCCC"
        m1 = ReflectiveGrid2D(
            initial,
            config=self.config,
            law=self.hierarchy,
            reflective_law=ReflectiveLaw(mirror_coupling=0.15, commit_delay=3),
        )
        m2 = MultiReflectiveGrid2D(
            initial,
            config=self.config,
            law=self.hierarchy,
            reflective_law=MultiReflectiveLaw(
                local_coupling=0.15,
                domain_coupling=0.0,
                system_coupling=0.0,
                local_commit_delay=3,
                domain_commit_delay=4,
                system_commit_delay=5,
            ),
        )
        m1.perturb_primary([12])
        m2.perturb_primary([12])
        for _ in range(6):
            m1.step(0.0)
            m2.step(0.0)
        self.assertEqual(m2.state_string(), m1.state_string())
        self.assertEqual(m2.local_mirror_string(), m1.mirror_string())

    def test_persistent_signal_recommits_all_reflection_levels(self) -> None:
        model = MultiReflectiveGrid2D(
            "A" * 25,
            config=self.config,
            law=self.hierarchy,
            reflective_law=MultiReflectiveLaw(
                local_coupling=0.15,
                domain_coupling=0.08,
                system_coupling=0.08,
                local_commit_delay=3,
                domain_commit_delay=4,
                system_commit_delay=5,
            ),
        )
        for _ in range(8):
            model.step(0.7)
        for _ in range(8):
            model.step(0.0)
        self.assertEqual(model.state_string(), "C" * 25)
        self.assertEqual(model.local_mirror_string(), "C" * 25)
        self.assertEqual(model.domain_mirror_string(), "C" * 25)
        self.assertEqual(model.system_mirror_string(), "C" * 25)
        self.assertGreater(model.domain_mirror_commit_events, 0)
        self.assertGreater(model.system_mirror_commit_events, 0)

    def test_perturbations_are_plane_specific(self) -> None:
        initial = "A" * 25
        model = MultiReflectiveGrid2D(
            initial,
            config=self.config,
            law=self.hierarchy,
            reflective_law=MultiReflectiveLaw(
                domain_coupling=0.08,
                system_coupling=0.08,
            ),
        )
        model.perturb_primary([0])
        model.perturb_local_mirror([1])
        model.perturb_domain_mirror([2])
        model.perturb_system_mirror([3])
        self.assertEqual(model.state_string()[0], "C")
        self.assertEqual(model.local_mirror_string()[1], "C")
        self.assertEqual(model.domain_mirror_string()[2], "C")
        self.assertEqual(model.system_mirror_string()[3], "C")
        self.assertEqual(model.local_mirror_string()[0], "A")
        self.assertEqual(model.domain_mirror_string()[0], "A")
        self.assertEqual(model.system_mirror_string()[0], "A")


if __name__ == "__main__":
    unittest.main()
