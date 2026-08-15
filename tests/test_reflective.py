from __future__ import annotations

import json
import unittest
from pathlib import Path

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalGrid2D, HierarchicalLaw
from morphos.reflective import ReflectiveGrid2D, ReflectiveLaw
from morphos.scale_aware import ScaleLaw

SUMMARY = Path("results/p1-reflective-v0.1-summary.json")

BASE = Grid2DConfig(
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
HIERARCHY = HierarchicalLaw(
    reference_linear_size=5.0,
    exponent=0.06,
    domain_size=3,
)


def config_for(size: int) -> Grid2DConfig:
    return ScaleLaw(
        reference_linear_size=5.0,
        exponent=0.25,
    ).apply(BASE, width=size, height=size)


class ReflectiveTests(unittest.TestCase):
    def test_invalid_reflective_parameters_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            ReflectiveLaw(mirror_coupling=-0.01)
        with self.assertRaises(ValueError):
            ReflectiveLaw(commit_delay=0)

    def test_zero_mirror_coupling_matches_s2_primary_dynamics(self) -> None:
        initial = "ACCAAACCCCACCCCACCCCACCAA"
        pulses = [0.0, 0.2, -0.1, 0.0, 0.0]
        baseline = HierarchicalGrid2D(
            initial,
            config=config_for(5),
            law=HIERARCHY,
        )
        reflective = ReflectiveGrid2D(
            initial,
            config=config_for(5),
            law=HIERARCHY,
            reflective_law=ReflectiveLaw(
                mirror_coupling=0.0,
                commit_delay=3,
            ),
        )
        for pulse in pulses:
            baseline.step(pulse)
            reflective.step(pulse)
            self.assertEqual(
                reflective.state_string(),
                baseline.state_string(),
            )

    def test_internal_mirror_recovers_a_locked_case_s2_misses(self) -> None:
        target = "ACCAAACCCCACCCCACCCCACCAA"
        index = 19

        corrupted = list(target)
        corrupted[index] = "C" if corrupted[index] == "A" else "A"
        baseline = HierarchicalGrid2D(
            "".join(corrupted),
            config=config_for(5),
            law=HIERARCHY,
        )
        baseline.run([0.0] * 6)

        reflective = ReflectiveGrid2D(
            target,
            config=config_for(5),
            law=HIERARCHY,
            reflective_law=ReflectiveLaw(),
        )
        reflective.perturb_primary([index])
        reflective.run([0.0] * 6)

        self.assertNotEqual(baseline.state_string(), target)
        self.assertEqual(reflective.state_string(), target)

    def test_co_corrupting_primary_and_mirror_removes_that_advantage(self) -> None:
        target = "ACCAAACCCCACCCCACCCCACCAA"
        index = 19
        reflective = ReflectiveGrid2D(
            target,
            config=config_for(5),
            law=HIERARCHY,
            reflective_law=ReflectiveLaw(),
        )
        reflective.perturb_primary([index])
        reflective.perturb_mirror([index])
        reflective.run([0.0] * 6)
        self.assertNotEqual(reflective.state_string(), target)

    def test_persistent_signal_recommits_the_self_image(self) -> None:
        model = ReflectiveGrid2D(
            "A" * 25,
            config=config_for(5),
            law=HIERARCHY,
            reflective_law=ReflectiveLaw(),
        )
        for _ in range(6):
            model.step(0.7)
        for _ in range(4):
            model.step(0.0)
        self.assertEqual(model.state_string(), "C" * 25)
        self.assertEqual(model.mirror_string(), "C" * 25)
        self.assertEqual(model.mirror_commits, 25)

    def test_committed_portable_summary_locks_declared_result(self) -> None:
        data = json.loads(SUMMARY.read_text(encoding="utf-8"))
        self.assertEqual(
            data["schema_version"],
            "cosmic-organics/reflective-summary-0.1",
        )
        self.assertEqual(data["quantization_decimals"], 9)
        self.assertEqual(
            data["evidence_digest"],
            "9479a44ed02e09c9aaa5b51566e296c9119b98e8cd7fcbc9c9551024afadd9a2",
        )
        self.assertTrue(
            data["summary"]["full_reflective_recovery_gate_pass"]
        )
        self.assertGreaterEqual(
            data["summary"]["min_recovery_gain"],
            0.15,
        )
        self.assertLessEqual(
            data["summary"]["max_abs_co_corruption_gain"],
            0.05,
        )


if __name__ == "__main__":
    unittest.main()
