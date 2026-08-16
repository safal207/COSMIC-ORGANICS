"""Print a compact summary of the W5 no-handoff observability diagnostic."""
from __future__ import annotations

import json

from benchmarks.diagnose_w5_no_handoff_observability import run_diagnostic


def main() -> None:
    report = run_diagnostic()
    cases = report["cases"]
    compact = {
        "schema": "cosmic-organics/w5-no-handoff-observability-compact-0.1",
        "case_count": report["case_count"],
        "category_counts": report["category_counts"],
        "by_size": report["by_size"],
        "all_cases_witness_unchanged": all(not case["witness_changed"] for case in cases),
        "all_cases_no_witness_commit": all(not case["witness_commit_seen"] for case in cases),
        "cases_with_zero_binary_observable_ticks": sum(case["binary_observable_ticks"] == 0 for case in cases),
        "cases_with_any_mixed_blind_ticks": sum(case["mixed_blind_ticks"] > 0 for case in cases),
        "cases_with_multi_error_state": sum(case["max_error_count"] > 1 for case in cases),
        "cases": [
            {
                "size": f'{case["width"]}x{case["height"]}',
                "seed": case["seed"],
                "target_index": case["target_index"],
                "trial_index": case["trial_index"],
                "source": case["source"],
                "source_anchor": case["source_anchor"],
                "category": case["category"],
                "mixed_blind_ticks": case["mixed_blind_ticks"],
                "binary_observable_ticks": case["binary_observable_ticks"],
                "max_error_count": case["max_error_count"],
                "witness_changed": case["witness_changed"],
                "witness_commit_seen": case["witness_commit_seen"],
                "residual_phases_at_8": case["residual_phases_at_8"],
                "residual_phases_at_12": case["residual_phases_at_12"],
                "syndrome_at_8": case["syndrome_at_8"],
                "syndrome_at_12": case["syndrome_at_12"],
            }
            for case in cases
        ],
    }
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
