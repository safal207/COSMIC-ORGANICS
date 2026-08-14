import unittest

from benchmarks.run_external_baselines import run_suite


class ExternalBaselineTests(unittest.TestCase):
    def test_current_tasks_show_no_distinct_advantage(self):
        result = run_suite()
        self.assertFalse(result["summary"]["distinct_advantage_observed"])
        self.assertEqual(result["summary"]["morphos_wins"], 0)
        self.assertEqual(result["summary"]["baseline_wins"], 0)
        self.assertEqual(result["summary"]["ties"], 3)

    def test_all_declared_tasks_are_solved_by_both(self):
        result = run_suite()
        for item in result["results"]:
            self.assertEqual(item["morphos"]["accuracy"], 1.0)
            self.assertEqual(item["baseline"]["accuracy"], 1.0)
            self.assertEqual(item["outcome"], "tie")

    def test_result_is_deterministic(self):
        first = run_suite()
        second = run_suite()
        self.assertEqual(first, second)
        self.assertEqual(
            first["result_digest"],
            "c3d59a8408c4c7c434c92450b61dd86438d017c61f1ddd9475e3ca2ff8b42e3b",
        )


if __name__ == "__main__":
    unittest.main()
