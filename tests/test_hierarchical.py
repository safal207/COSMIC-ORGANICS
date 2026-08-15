from __future__ import annotations

import json
import unittest
from pathlib import Path

from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.hierarchical import HierarchicalGrid2D, HierarchicalLaw

MANIFEST = Path(__file__).parents[1] / "benchmarks" / "hierarchical_manifest.json"
SUMMARY = Path(__file__).parents[1] / "results" / "p1-hierarchical-v0.1-summary.json"


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

    def test_frozen_manifest_has_discovery_boundary(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        discovery = manifest["discovery"]
        self.assertEqual(discovery["domain_size"], 3)
        self.assertIn(0.06, discovery["hierarchy_exponents"])
        self.assertIn(0.07, discovery["hierarchy_exponents"])
        self.assertEqual(len(discovery["sizes"]), 3)
        self.assertEqual(len(manifest["confirmation"]["sizes"]), 3)

    def test_committed_summary_locks_expected_gates(self) -> None:
        summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        self.assertEqual(
            summary["schema_version"],
            "cosmic-organics/hierarchical-summary-0.2",
        )
        self.assertEqual(
            summary["portable_identity_scope"],
            "quantized_scientific_summary",
        )
        self.assertEqual(summary["quantization_decimals"], 9)
        self.assertEqual(
            summary["evidence_digest"],
            "c7bc7d20863f3da306d1b308887a7711e409bd399ebe82d77b758af4edc0bd37",
        )
        gates = summary["summary"]
        self.assertTrue(gates["large_scale_capacity_gate_pass"])
        self.assertTrue(gates["large_scale_recovery_gain_gate_pass"])
        self.assertFalse(gates["recovery_parity_gate_pass"])
        self.assertFalse(gates["full_hierarchical_generalization_pass"])


if __name__ == "__main__":
    unittest.main()
