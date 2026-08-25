import unittest
from benchmarks.run_scale_aware import run_suite
from morphos.grid2d import Grid2DConfig
from morphos.scale_aware import ScaleLaw

class ScaleAwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_suite()

    def test_discovery_selects_minimum_passing_exponent(self):
        discovery = self.result["discovery"]
        passing = [row["exponent"] for row in discovery if row["passes"]]
        self.assertEqual(min(passing), 0.25)
        self.assertEqual(self.result["summary"]["selected_exponent"], 0.25)

    def test_reference_size_preserves_frozen_couplings(self):
        base = Grid2DConfig(anchor_coupling=0.75, adaptive_coupling=0.5)
        scaled = ScaleLaw(reference_linear_size=5.0, exponent=0.25).apply(base, width=5, height=5)
        self.assertEqual(scaled.anchor_coupling, 0.75)
        self.assertEqual(scaled.adaptive_coupling, 0.5)

    def test_scale_factor_decreases_monotonically(self):
        law = ScaleLaw(reference_linear_size=5.0, exponent=0.25)
        self.assertEqual(law.factor(5, 5), 1.0)
        self.assertGreater(law.factor(5, 5), law.factor(7, 7))
        self.assertGreater(law.factor(7, 7), law.factor(9, 9))

    def test_scale_capacity_gate_repairs_frozen_failures(self):
        summary = self.result["summary"]
        self.assertGreater(summary["frozen_capacity_failure_corpora"], 0)
        self.assertEqual(summary["scale_aware_capacity_failure_corpora"], 0)
        self.assertTrue(summary["scale_capacity_gate_pass"])

    def test_recovery_tradeoff_remains_explicit(self):
        summary = self.result["summary"]
        self.assertFalse(summary["recovery_gate_pass"])
        self.assertFalse(summary["full_scale_generalization_pass"])
        self.assertLess(summary["mean_recovery_delta"], 0)
        self.assertLess(summary["mean_recovery_cost_ratio"], 1)

    def test_confirmation_has_nine_frozen_corpora(self):
        self.assertEqual(self.result["summary"]["confirmation_corpora"], 9)
        self.assertTrue(self.result["summary"]["all_confirmation_capacity_deltas_positive"])
        self.assertTrue(self.result["summary"]["all_confirmation_seed_cost_ratios_below_one"])

    def test_result_digest_is_deterministic(self):
        second = run_suite()
        self.assertEqual(self.result, second)
        self.assertEqual(self.result["result_digest"], "87fcf34923727eca1f6129014b53796695b82d05055e708a06fb0d8cdc7c115a")

if __name__ == "__main__":
    unittest.main()
