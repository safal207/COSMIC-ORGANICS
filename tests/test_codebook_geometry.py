from __future__ import annotations

import json
import unittest
from pathlib import Path

from benchmarks.run_codebook_geometry import (
    DEFAULT_MANIFEST,
    codebook_geometry,
    hamming,
    one_bit_geometry_trials,
)


class CodebookGeometryTests(unittest.TestCase):
    def test_hamming_distance(self) -> None:
        self.assertEqual(hamming("AAA", "CCC"), 3)
        self.assertEqual(hamming("ACA", "ACC"), 1)

    def test_distance_three_supports_single_bit_unique_decoding(self) -> None:
        geometry = codebook_geometry(["AAA", "CCC"])
        self.assertEqual(geometry["min_distance"], 3)
        self.assertTrue(geometry["distance3_single_bit_guarantee"])
        report = one_bit_geometry_trials(
            ["AAA", "CCC"],
            lambda state: (state, 0),
            seed=1,
            model_name="synthetic",
            trial_cap=100,
        )
        self.assertEqual(report["unique_nearest_fraction"], 1.0)
        self.assertEqual(report["direct_codeword_collision_fraction"], 0.0)

    def test_distance_one_creates_direct_codeword_collision(self) -> None:
        geometry = codebook_geometry(["AAA", "AAC"])
        self.assertEqual(geometry["min_distance"], 1)
        self.assertFalse(geometry["distance3_single_bit_guarantee"])
        report = one_bit_geometry_trials(
            ["AAA", "AAC"],
            lambda state: (state, 0),
            seed=2,
            model_name="synthetic",
            trial_cap=100,
        )
        self.assertGreater(report["direct_codeword_collision_fraction"], 0.0)
        self.assertEqual(report["dynamic_recovery_on_direct_collision"], 0.0)

    def test_manifest_is_diagnostic_only_and_uses_fresh_seeds(self) -> None:
        manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        self.assertIn("diagnostic-only", manifest["analysis"]["selection_rule"])
        seeds = [
            seed
            for size in manifest["analysis"]["sizes"]
            for seed in size["seeds"]
        ]
        self.assertEqual(len(seeds), len(set(seeds)))
        self.assertTrue(all(str(seed).startswith("20260825") for seed in seeds))
        self.assertEqual(manifest["s2_hierarchy_law"]["exponent"], 0.06)
        self.assertEqual(manifest["s2_hierarchy_law"]["domain_size"], 3)


if __name__ == "__main__":
    unittest.main()
