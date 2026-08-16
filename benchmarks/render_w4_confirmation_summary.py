"""Render portable quantized MORPHOS-W4 confirmation evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

DECIMALS = 9


def _quantize(value):
    if isinstance(value, float):
        return round(value, DECIMALS)
    if isinstance(value, list):
        return [_quantize(item) for item in value]
    if isinstance(value, dict):
        return {key: _quantize(item) for key, item in value.items()}
    return value


def render(report: dict) -> dict:
    rows = []
    for row in report["rows"]:
        rows.append({
            "width": row["width"],
            "height": row["height"],
            "seed": row["seed"],
            "single_bit_trials": row["single_bit_trials"],
            "w4_common_8": row["w4_common_8"],
            "w4_common_12": row["w4_common_12"],
            "gain_vs_w3_at_8": row["gain_vs_w3_at_8"],
            "primary_gain_vs_m2": row["primary_gain_vs_m2"],
            "retention_delta_12_minus_8": row["retention_delta_12_minus_8"],
            "causal_drop_when_witness_corrupted": row[
                "causal_drop_when_witness_corrupted"
            ],
            "zero_drive_delta_vs_m2": row["zero_drive_delta_vs_m2"],
            "fence_release_fraction_8": row["fence_release_fraction_8"],
            "fence_release_fraction_12": row["fence_release_fraction_12"],
            "two_bit_diagnostic": row["two_bit_diagnostic"],
        })

    portable = _quantize({
        "schema": "cosmic-organics/w4-confirmation-summary-0.1",
        "portable_identity_scope": "quantized_scientific_summary",
        "quantization_decimals": DECIMALS,
        "frozen_from_head": report["frozen_from_head"],
        "confirmation_only_no_retuning": report["confirmation_only_no_retuning"],
        "criteria": report["criteria"],
        "rows": rows,
        "summary": report["summary"],
        "passes": report["passes"],
        "diagnostic_note": report["diagnostic_note"],
    })
    canonical = json.dumps(
        portable, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    portable["portable_evidence_digest"] = hashlib.sha256(canonical).hexdigest()
    return portable


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    result = render(report)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
