import json
from pathlib import Path
import unittest

from benchmarks.run import run_suite


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkTests(unittest.TestCase):
    def test_committed_result_is_reproducible(self):
        actual = run_suite(ROOT / "benchmarks" / "manifest.json")
        expected = json.loads(
            (ROOT / "results" / "p1-baseline-v0.1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(actual, expected)

    def test_defect_repair_beats_uncoupled_baseline(self):
        report = run_suite(ROOT / "benchmarks" / "manifest.json")
        result = next(item for item in report["results"] if item["id"] == "defect-repair")
        self.assertEqual(result["morphos"]["accuracy"], 1.0)
        self.assertGreater(result["accuracy_delta"], 0.0)

    def test_subthreshold_accumulation_is_recorded_as_failure(self):
        report = run_suite(ROOT / "benchmarks" / "manifest.json")
        self.assertIn("subthreshold-accumulation", report["summary"]["known_failure_cases"])
        result = next(
            item for item in report["results"] if item["id"] == "subthreshold-accumulation"
        )
        self.assertFalse(result["criterion_passed"])


if __name__ == "__main__":
    unittest.main()
