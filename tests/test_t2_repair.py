import unittest

from benchmarks.run_t2_repair import run_suite
from morphos.simulator import Phase
from morphos.temporal_t2 import T2Config, T2Lattice


class T2RepairTests(unittest.TestCase):
    def test_grid_counts_are_locked(self):
        result = run_suite()
        self.assertEqual(result["grid"]["points"], 243)
        self.assertEqual(result["summary"]["all_gate_points"], 85)
        self.assertEqual(result["summary"]["capacity_matched_points"], 6)
        self.assertEqual(result["summary"]["recovery_beating_points"], 57)
        self.assertEqual(result["summary"]["dead_zone_free_points"], 8)
        self.assertEqual(result["summary"]["dominates_majority_points"], 0)

    def test_capacity_matched_candidate_ties_baseline_but_costs_more(self):
        result = run_suite()
        candidate = result["selected_candidates"]["capacity_matched"]
        baseline = result["baseline"]
        self.assertEqual(candidate["capacity_bits"], baseline["capacity_bits"])
        self.assertEqual(
            candidate["one_bit_recovery_rate"], baseline["one_bit_recovery_rate"]
        )
        self.assertGreater(
            candidate["average_relaxation_transition_cost"],
            baseline["average_relaxation_transition_cost"],
        )

    def test_recovery_biased_candidate_trades_capacity_and_cost(self):
        result = run_suite()
        candidate = result["selected_candidates"]["recovery_biased"]
        baseline = result["baseline"]
        self.assertGreater(
            candidate["one_bit_recovery_rate"], baseline["one_bit_recovery_rate"]
        )
        self.assertLess(candidate["capacity_bits"], baseline["capacity_bits"])
        self.assertGreater(
            candidate["average_relaxation_transition_cost"],
            baseline["average_relaxation_transition_cost"],
        )

    def test_dead_zone_free_candidate_exists_but_has_low_capacity(self):
        result = run_suite()
        candidate = result["selected_candidates"]["dead_zone_free"]
        self.assertEqual(candidate["mixed_dead_zone_fraction"], 0.0)
        self.assertEqual(candidate["one_bit_recovery_rate"], 1.0)
        self.assertEqual(candidate["capacity_bits"], 1.0)

    def test_t2_config_validation(self):
        with self.assertRaises(ValueError):
            T2Config(mixed_relax_threshold=0.0)
        lattice = T2Lattice(size=1, initial=Phase.MIXED, config=T2Config())
        self.assertEqual(lattice.phase_string(), "M")

    def test_result_digest_is_deterministic(self):
        first = run_suite()
        second = run_suite()
        self.assertEqual(first, second)
        self.assertEqual(
            first["result_digest"],
            "e70a5547ca58c0601e796dd233922bbc2580470629c830f5f1d9b2bbe38d370d",
        )


if __name__ == "__main__":
    unittest.main()
