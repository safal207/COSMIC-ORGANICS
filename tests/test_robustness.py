import json
import unittest

from benchmarks.run_robustness import DEFAULT_MANIFEST, evaluate_point, run_suite


def _tasks():
    return json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))["locked_tasks"]


class RobustnessTests(unittest.TestCase):
    def test_grid_size_and_stable_region_are_locked(self):
        result = run_suite()
        self.assertEqual(result["grid"]["points"], 400)
        self.assertEqual(result["summary"]["stable_points"], 20)
        self.assertEqual(result["summary"]["stable_fraction"], 0.05)

    def test_criterion_counts_are_locked(self):
        result = run_suite()
        self.assertEqual(
            result["summary"]["criterion_pass_counts"],
            {
                "alternating_pulse_cancellation": 375,
                "defect_repair": 80,
                "isolated_pulse_decay": 375,
                "subthreshold_accumulation": 95,
                "zero_input_stability": 400,
            },
        )

    def test_known_full_pass_configuration(self):
        result = evaluate_point(0.8, 0.35, 1.0, 0.2, _tasks())
        self.assertTrue(result["all_gates"])

    def test_nominal_temporal_config_is_not_overclaimed(self):
        result = evaluate_point(0.8, 0.35, 0.35, 0.2, _tasks())
        self.assertTrue(result["passes"]["subthreshold_accumulation"])
        self.assertFalse(result["passes"]["defect_repair"])
        self.assertFalse(result["all_gates"])

    def test_result_digest_is_deterministic(self):
        first = run_suite()
        second = run_suite()
        self.assertEqual(first, second)
        self.assertEqual(len(first["grid_digest"]), 64)
        self.assertEqual(len(first["result_digest"]), 64)


if __name__ == "__main__":
    unittest.main()
