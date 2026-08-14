import unittest

from benchmarks.run_state_capacity import run_suite


class StateCapacityTests(unittest.TestCase):
    def test_capacity_tradeoff_is_locked(self):
        result = run_suite()
        sweep = {item["coupling"]: item for item in result["morphos_sweep"]}
        self.assertEqual(sweep[0.0]["stable_states"], 128)
        self.assertEqual(sweep[0.25]["stable_states"], 128)
        self.assertEqual(sweep[0.5]["stable_states"], 16)
        self.assertEqual(sweep[1.0]["stable_states"], 2)

    def test_robust_configuration_has_mixed_dead_zone(self):
        result = run_suite()
        robust = result["summary"]["robust_config"]
        self.assertEqual(robust["capacity_bits"], 1.0)
        self.assertEqual(robust["one_bit_recovery_rate"], 0.0)
        self.assertEqual(robust["mixed_dead_zone_fraction"], 1.0)

    def test_majority_baseline_recovers_some_single_bit_errors(self):
        result = run_suite()
        majority = result["summary"]["majority_ca"]
        self.assertEqual(majority["capacity_bits"], 4.0)
        self.assertEqual(majority["one_bit_recovery_rate"], 0.375)

    def test_no_advantage_is_overclaimed(self):
        result = run_suite()
        self.assertFalse(result["summary"]["capacity_advantage_observed"])
        self.assertFalse(result["summary"]["noise_advantage_observed"])
        self.assertTrue(result["summary"]["mixed_dead_zone_detected"])

    def test_digest_is_deterministic(self):
        first = run_suite()
        second = run_suite()
        self.assertEqual(first, second)
        self.assertEqual(
            first["result_digest"],
            "3a3e4a783c2a3869cb5cfe92191ff6b597d9167652e08eb13cf283a44179e3eb",
        )


if __name__ == "__main__":
    unittest.main()
