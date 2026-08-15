from __future__ import annotations

import unittest

from benchmarks.run_hierarchical import run_suite
from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.hierarchical import HierarchicalGrid2D, HierarchicalLaw


class HierarchicalLawTests(unittest.TestCase):
    def test_reference_size_factor_is_one(self) -> None:
        law = HierarchicalLaw(
            reference_linear_size=5.0,
            exponent=0.06,
            domain_size=3,
        )
        self.assertEqual(law.intra_factor(5, 5), 1.0)
        self.assertGreater(law.intra_factor(9, 9), 1.0)

    def test_invalid_parameters_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            HierarchicalLaw(reference_linear_size=0)
        with self.assertRaises(ValueError):
            HierarchicalLaw(exponent=-0.1)
        with self.assertRaises(ValueError):
            HierarchicalLaw(domain_size=0)

    def test_reference_size_dynamics_match_s1(self) -> None:
        initial = "ACACA" "CACAC" "AACCC" "CCAAA" "ACCCA"
        config = Grid2DConfig(width=5, height=5)
        baseline = Grid2D(initial, config=config)
        candidate = HierarchicalGrid2D(
            initial,
            config=config,
            law=HierarchicalLaw(
                reference_linear_size=5.0,
                exponent=0.06,
                domain_size=3,
            ),
        )
        baseline.run([0.0] * 6)
        candidate.run([0.0] * 6)
        self.assertEqual(candidate.state_string(), baseline.state_string())
        self.assertEqual(candidate.transitions, baseline.transitions)


class HierarchicalBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = run_suite()

    def test_discovery_selects_capacity_bounded_exponent(self) -> None:
        self.assertEqual(
            self.report["summary"]["selected_hierarchy_exponent"],
            0.06,
        )
        by_exponent = {
            row["hierarchy_exponent"]: row
            for row in self.report["discovery"]
        }
        self.assertTrue(by_exponent[0.06]["passes"])
        self.assertFalse(by_exponent[0.07]["passes"])

    def test_large_scale_recovery_improves_without_closing_gate(self) -> None:
        summary = self.report["summary"]
        self.assertTrue(summary["large_scale_capacity_gate_pass"])
        self.assertTrue(summary["large_scale_recovery_gain_gate_pass"])
        self.assertFalse(summary["recovery_parity_gate_pass"])
        self.assertFalse(
            summary["full_hierarchical_generalization_pass"]
        )
        self.assertEqual(
            summary["fresh_5x5_capacity_failure_corpora"],
            1,
        )
        self.assertEqual(
            summary["s1_fresh_5x5_capacity_failure_corpora"],
            1,
        )

    def test_locked_summary_and_digest(self) -> None:
        summary = self.report["summary"]
        self.assertEqual(
            summary["mean_capacity_delta_bits"],
            0.468885075994,
        )
        self.assertEqual(
            summary["large_scale_mean_recovery_gain_vs_s1"],
            0.047131890716,
        )
        self.assertEqual(
            summary["large_scale_min_capacity_delta_bits"],
            0.289506617195,
        )
        self.assertEqual(
            self.report["result_digest"],
            "f41a4e73ce88041a2608a27dab4207e913f297bd1dbc0acc875fa9662e140a3b",
        )


if __name__ == "__main__":
    unittest.main()
