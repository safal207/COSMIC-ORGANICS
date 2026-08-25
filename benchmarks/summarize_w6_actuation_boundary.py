"""Print a compact causal summary for the frozen W6 actuation diagnostic."""
from __future__ import annotations

import json

from benchmarks.diagnose_w6_actuation_boundary import run_diagnostic


def main() -> None:
    report = run_diagnostic()
    cases = report["cases"]
    rows = []
    for case in cases:
        first = case["first_actuation_sample"] or {}
        samples = case["actuation_samples"]
        rows.append(
            {
                "size": f'{case["width"]}x{case["height"]}',
                "seed": case["seed"],
                "target_index": case["target_index"],
                "trial_index": case["trial_index"],
                "source": case["source"],
                "erasure_owner": case["first_erasure_owner"],
                "handoff_tick": case["first_erasure_handoff_tick"],
                "target_phase": case["target_phase"],
                "classification": case["classification"],
                "anchor": first.get("anchor"),
                "neighbor_same_target_count": first.get("neighbor_same_target_count"),
                "witness_drive": first.get("witness_drive"),
                "neighbor_drive": first.get("neighbor_drive"),
                "mirror_drive": first.get("mirror_drive"),
                "signed_total_drive_toward_target": first.get("signed_total_drive_toward_target"),
                "activation_before": first.get("activation_before"),
                "signed_activation_candidate_toward_target": first.get("signed_activation_toward_target"),
                "mixed_relax_threshold": first.get("mixed_relax_threshold"),
                "first_threshold_crossing": first.get("threshold_crossing_toward_target"),
                "sample_count": len(samples),
                "max_signed_activation_toward_target": max(
                    (sample["signed_activation_toward_target"] for sample in samples),
                    default=None,
                ),
                "max_signed_total_drive_toward_target": max(
                    (sample["signed_total_drive_toward_target"] for sample in samples),
                    default=None,
                ),
                "min_signed_total_drive_toward_target": min(
                    (sample["signed_total_drive_toward_target"] for sample in samples),
                    default=None,
                ),
                "endpoint_seen": case["target_seen_after_handoff"],
                "exact_at_8": case["exact_at_8"],
                "exact_at_12": case["exact_at_12"],
            }
        )

    positive_drive_negative_activation = sum(
        row["signed_total_drive_toward_target"] is not None
        and row["signed_total_drive_toward_target"] > 0
        and row["signed_activation_candidate_toward_target"] is not None
        and row["signed_activation_candidate_toward_target"] < 0
        for row in rows
    )
    thresholds = sorted(
        {row["mixed_relax_threshold"] for row in rows if row["mixed_relax_threshold"] is not None}
    )
    compact = {
        "schema": "cosmic-organics/w6-actuation-boundary-compact-0.1",
        "case_count": report["case_count"],
        "classification_counts": report["classification_counts"],
        "handoff_tick_counts": report["handoff_tick_counts"],
        "thresholds": thresholds,
        "positive_current_drive_but_negative_accumulated_activation_count": positive_drive_negative_activation,
        "first_signed_total_drive_range": [
            min(row["signed_total_drive_toward_target"] for row in rows),
            max(row["signed_total_drive_toward_target"] for row in rows),
        ],
        "first_signed_activation_candidate_range": [
            min(row["signed_activation_candidate_toward_target"] for row in rows),
            max(row["signed_activation_candidate_toward_target"] for row in rows),
        ],
        "first_activation_before_range": [
            min(row["activation_before"] for row in rows),
            max(row["activation_before"] for row in rows),
        ],
        "first_threshold_crossing_count": sum(bool(row["first_threshold_crossing"]) for row in rows),
        "endpoint_seen_count": sum(bool(row["endpoint_seen"]) for row in rows),
        "exact_at_8_count": sum(bool(row["exact_at_8"]) for row in rows),
        "exact_at_12_count": sum(bool(row["exact_at_12"]) for row in rows),
        "cases": rows,
    }
    print(json.dumps(compact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
