from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks import cosmic_hw_14_candidate as candidate


class CosmicHw14CandidateTests(unittest.TestCase):
    def test_load_manifest_rejects_capacity_for_another_density(self) -> None:
        manifest = json.loads(candidate.MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest["target"]["density_flag"] = "--45k"

        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(candidate, "MANIFEST_PATH", manifest_path):
                with self.assertRaisesRegex(
                    RuntimeError, "supports only density_flag '--85k'"
                ):
                    candidate.load_manifest()

    def test_evidence_summary_finishes_table_before_fmax_lines(self) -> None:
        profiles = {}
        for index, name in enumerate(
            ("CORE_LITE_R40", "PROOF_EDGE_SHA1", "FULL_PROOF_HMAC"),
            start=1,
        ):
            profiles[name] = {
                "harness_synthesis": {
                    "trellis_comb": index * 10,
                    "trellis_ff": index * 20,
                    "mult18x18d": index,
                },
                "physical": {
                    "successful_routes": index,
                    "packed_bitstreams": index,
                    "timing_10mhz_passes": index,
                    "maximum_resource_fractions": {
                        "comb": 0.1 * index,
                        "ff": 0.2 * index,
                        "mult": 0.05 * index,
                    },
                    "headroom_pass": index < 3,
                    "board_handoff_eligible": index == 2,
                    "fmax_mhz": {
                        "minimum": 10.0 + index,
                        "median": 11.0 + index,
                        "maximum": 12.0 + index,
                    },
                },
            }

        rendered = candidate.render_evidence_summary(
            {
                "decision": "PROOF_EDGE_BOARD_HANDOFF_SUPPORTED",
                "selected_board_handoff_profile": "PROOF_EDGE_SHA1",
                "profiles": profiles,
            }
        )
        lines = rendered.splitlines()
        table_rows = [
            index for index, line in enumerate(lines) if line.startswith("|")
        ]
        fmax_rows = [
            index
            for index, line in enumerate(lines)
            if " routed Fmax min/median/max: " in line
        ]

        self.assertEqual(len(table_rows), 5)
        self.assertEqual(
            table_rows, list(range(table_rows[0], table_rows[0] + 5))
        )
        self.assertEqual(lines[table_rows[-1] + 1], "")
        self.assertEqual(len(fmax_rows), 3)
        self.assertGreater(min(fmax_rows), table_rows[-1] + 1)


if __name__ == "__main__":
    unittest.main()
