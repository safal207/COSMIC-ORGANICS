"""Render portable MORPHOS-M2 scientific evidence summary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.run_multimirror import run_suite

QUANTIZATION_DECIMALS = 9


def _quantize(value):
    if isinstance(value, float):
        return round(value, QUANTIZATION_DECIMALS)
    if isinstance(value, list):
        return [_quantize(item) for item in value]
    if isinstance(value, dict):
        return {key: _quantize(item) for key, item in value.items()}
    return value


def render_summary(report: dict | None = None) -> dict:
    if report is None:
        report = run_suite()
    payload = {
        "schema_version": "cosmic-organics/multimirror-summary-0.1",
        "suite_id": report["suite_id"],
        "parameter_status": report["parameter_status"],
        "portable_identity_scope": "quantized_scientific_summary",
        "quantization_decimals": QUANTIZATION_DECIMALS,
        "mechanism": {
            "external_oracle": False,
            "phase_planes": 4,
            "local_coupling": 0.15,
            "domain_coupling": 0.08,
            "system_coupling": 0.08,
            "local_commit_delay": 3,
            "domain_commit_delay": 4,
            "system_commit_delay": 5,
        },
        "confirmation": [
            {
                key: row[key]
                for key in (
                    "width",
                    "height",
                    "seed",
                    "trials",
                    "s2_recovery_1bit",
                    "m1_primary_recovery_1bit",
                    "m1_co_recovery_1bit",
                    "m2_primary_recovery_1bit",
                    "m2_double_recovery_1bit",
                    "m2_domain_only_recovery_1bit",
                    "m2_system_only_recovery_1bit",
                    "m2_all_corrupted_recovery_1bit",
                    "primary_gain_vs_m1",
                    "double_gain_vs_m1_co",
                    "domain_only_gain_vs_m1_co",
                    "system_only_gain_vs_m1_co",
                    "all_corruption_gain_vs_s2",
                    "primary_transition_cost_ratio_vs_m1",
                    "double_transition_cost_ratio_vs_m1_co",
                )
            }
            for row in report["confirmation"]
        ],
        "adaptation": report["adaptation"],
        "summary": report["summary"],
    }
    payload = _quantize(payload)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    payload["evidence_digest"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = None
    if args.report:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    rendered = json.dumps(render_summary(report), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
