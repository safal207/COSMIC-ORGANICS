import json
import unittest

from benchmarks.run_2d_heterogeneous import DEFAULT_MANIFEST, run_suite
from morphos.grid2d import Grid2D, Grid2DConfig


class Heterogeneous2DTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_suite()

    def test_structured_candidate_beats_majority_on_recovery_and_cost(self):
        candidate = self.result["structured"]["heterogeneous_checkerboard"]
        majority = self.result["structured"]["majority_ca"]
        self.assertEqual(candidate["stable_pattern_count"], majority["stable_pattern_count"])
        self.assertGreater(candidate["one_bit_recovery_rate"], majority["one_bit_recovery_rate"])
        self.assertLess(candidate["average_recovery_transition_cost"], majority["average_recovery_transition_cost"])

    def test_confirmation_is_tradeoff_not_full_dominance(self):
        candidate = self.result["confirmation"]["heterogeneous_checkerboard"]
        majority = self.result["confirmation"]["majority_ca"]
        self.assertGreater(candidate["binary_fixed_attractors"], majority["binary_fixed_attractors"])
        self.assertLess(candidate["one_bit_recovery"], majority["one_bit_recovery"])
        self.assertLess(candidate["recovery_cost"], majority["recovery_cost"])
        self.assertTrue(self.result["summary"]["candidate_pareto_nondominated"])
        self.assertFalse(self.result["summary"]["full_dominance_observed"])

    def test_homogeneous_ablations_bound_the_tradeoff(self):
        candidate = self.result["confirmation"]["heterogeneous_checkerboard"]
        anchor = self.result["confirmation"]["homogeneous_anchor"]
        adaptive = self.result["confirmation"]["homogeneous_adaptive"]
        self.assertGreater(candidate["binary_capacity_bits"], anchor["binary_capacity_bits"])
        self.assertLess(candidate["one_bit_recovery"], anchor["one_bit_recovery"])
        self.assertLess(candidate["binary_capacity_bits"], adaptive["binary_capacity_bits"])
        self.assertGreater(candidate["one_bit_recovery"], adaptive["one_bit_recovery"])

    def test_manifest_uses_crypto_deterministic_confirmation_generator(self):
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["confirmation"]["generator"], "sha256-indexed-bits")
        self.assertEqual(manifest["confirmation"]["samples"], 256)
        self.assertEqual(manifest["selection_provenance"]["confirmation_seed"], 2026081402)

    def test_grid_validation_and_synchronous_shape(self):
        with self.assertRaises(ValueError):
            Grid2DConfig(width=0)
        config = Grid2DConfig(width=2, height=2)
        lattice = Grid2D("AAAA", config=config)
        lattice.step(0.0)
        self.assertEqual(lattice.state_string(), "AAAA")

    def test_result_digest_is_deterministic(self):
        second = run_suite()
        self.assertEqual(self.result, second)
        self.assertEqual(self.result["result_digest"], "47b0b631df4f47450c1530638e3ebe17dc3d7da2872aeeefe3e4c2b7b9fc9d3a")


if __name__ == "__main__":
    unittest.main()
