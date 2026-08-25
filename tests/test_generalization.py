import unittest

from benchmarks.render_generalization_summary import render_summary
from benchmarks.run_generalization import run_suite
from morphos.grid2d import Grid2DConfig


class GeneralizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_suite()
        cls.evidence = render_summary()

    def test_multi_seed_transfer_is_consistent_but_recovery_tradeoff_remains(self):
        summary = self.result["multi_seed"]["summary"]
        self.assertTrue(summary["seed_transfer_gate_pass"])
        self.assertTrue(summary["all_capacity_deltas_positive"])
        self.assertTrue(summary["all_recovery_deltas_negative"])
        self.assertTrue(summary["all_seed_cost_ratios_below_one"])

    def test_scaling_gate_is_explicitly_failed(self):
        summary = self.result["scale"]["summary"]
        self.assertEqual(summary["capacity_advantage_sizes"], [5])
        self.assertFalse(summary["scaling_gate_pass"])

    def test_multibit_noise_is_cheaper_but_not_more_accurate(self):
        summary = self.result["multi_bit_noise"]["summary"]
        self.assertFalse(summary["candidate_recovery_above_majority_for_all_bits"])
        self.assertTrue(summary["candidate_recovery_cost_below_majority_for_all_bits"])

    def test_recurrent_challenge_preserves_pareto_status_without_dominance(self):
        summary = self.result["recurrent_challenge"]["summary"]
        self.assertEqual(summary["discovery_parameter_points"], 15)
        self.assertEqual(summary["discovery_unique_regimes"], 3)
        self.assertTrue(summary["candidate_pareto_nondominated_on_confirmation"])
        self.assertFalse(summary["candidate_fully_dominates_recurrent_frontier"])

    def test_new_masks_and_neighborhoods_are_declared(self):
        self.assertEqual(Grid2DConfig(mask="row_stripes").mask, "row_stripes")
        self.assertEqual(Grid2DConfig(mask="column_stripes").mask, "column_stripes")
        self.assertEqual(Grid2DConfig(mask="quadrants").mask, "quadrants")
        self.assertEqual(Grid2DConfig(neighborhood="moore").neighborhood, "moore")
        with self.assertRaises(ValueError):
            Grid2DConfig(mask="unknown")
        with self.assertRaises(ValueError):
            Grid2DConfig(neighborhood="unknown")

    def test_full_generalization_gate_remains_closed_and_evidence_is_locked(self):
        summary = self.result["summary"]
        self.assertTrue(summary["seed_transfer_gate_pass"])
        self.assertFalse(summary["scaling_gate_pass"])
        self.assertFalse(summary["multi_bit_recovery_gate_pass"])
        self.assertTrue(summary["multi_bit_cost_gate_pass"])
        self.assertTrue(summary["recurrent_pareto_gate_pass"])
        self.assertFalse(summary["full_generalization_gate_pass"])
        self.assertEqual(
            self.evidence["evidence_digest"],
            "953e38a05958f970386bd256b964ade1d9240b3ff134da696bf8d9942e9850c0",
        )


if __name__ == "__main__":
    unittest.main()
