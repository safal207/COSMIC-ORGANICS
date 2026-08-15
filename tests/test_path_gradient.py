from __future__ import annotations

import unittest

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalLaw
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw
from morphos.path_gradient import PathGradientGrid2D, PathGradientLaw


class PathGradientTests(unittest.TestCase):
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

    def test_negative_gradient_gain_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            PathGradientLaw(gradient_gain=-0.1)

    def test_zero_gain_matches_m2_primary_dynamics(self) -> None:
        target = "C" * 25
        m2 = MultiReflectiveGrid2D(
            target,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
        )
        p1 = PathGradientGrid2D(
            target,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
            path_law=PathGradientLaw(gradient_gain=0.0),
        )
        m2.perturb_primary([12])
        p1.perturb_primary([12])
        for _ in range(6):
            m2.step(0.0)
            p1.step(0.0)
        self.assertEqual(p1.state_string(), m2.state_string())
        self.assertEqual(p1.local_mirror_string(), m2.local_mirror_string())
        self.assertEqual(p1.domain_mirror_string(), m2.domain_mirror_string())
        self.assertEqual(p1.system_mirror_string(), m2.system_mirror_string())

    def test_primary_perturbation_activates_path_feedback(self) -> None:
        model = PathGradientGrid2D(
            "C" * 25,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
            path_law=PathGradientLaw(gradient_gain=0.5),
        )
        model.perturb_primary([12])
        self.assertGreater(model.reflection_distance(), 0.0)
        model.step(0.0)
        self.assertGreater(model.last_path_multiplier, 1.0)
        self.assertEqual(model.boosted_steps, 1)

    def test_all_plane_corruption_has_no_false_path_signal(self) -> None:
        target = "C" * 25
        model = PathGradientGrid2D(
            target,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
            path_law=PathGradientLaw(gradient_gain=1.0),
        )
        for perturb in (
            model.perturb_primary,
            model.perturb_local_mirror,
            model.perturb_domain_mirror,
            model.perturb_system_mirror,
        ):
            perturb([12])
        self.assertEqual(model.reflection_distance(), 0.0)
        model.step(0.0)
        self.assertEqual(model.last_path_multiplier, 1.0)
        self.assertEqual(model.boosted_steps, 0)

    def test_persistent_signal_can_rewrite_the_path(self) -> None:
        model = PathGradientGrid2D(
            "A" * 25,
            config=self.config,
            law=self.hierarchy,
            reflective_law=self.m2_law,
            path_law=PathGradientLaw(gradient_gain=0.5),
        )
        for _ in range(10):
            model.step(0.7)
        for _ in range(10):
            model.step(0.0)
        self.assertEqual(model.state_string(), "C" * 25)
        self.assertEqual(model.local_mirror_string(), "C" * 25)
        self.assertEqual(model.domain_mirror_string(), "C" * 25)
        self.assertEqual(model.system_mirror_string(), "C" * 25)


if __name__ == "__main__":
    unittest.main()
