"""Render the portable MORPHOS-M1 evidence envelope."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.run_reflective import run_suite

QUANTIZATION_DECIMALS = 9


def _quantize(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, QUANTIZATION_DECIMALS)
    if isinstance(value, list):
        return [_quantize(item) for item in value]
    if isinstance(value, dict):
        return {key: _quantize(item) for key, item in value.items()}
    return value


def render_summary(report: dict[str, Any] | None = None) -> dict[str, Any]:
    if report is None:
        report = run_suite()

    payload = {
        "schema_version": "cosmic-organics/reflective-summary-0.1",
        "suite_id": report["suite_id"],
        "portable_identity_scope": "quantized_scientific_summary",
        "quantization_decimals": QUANTIZATION_DECIMALS,
        "mechanism": {
            "mirror_coupling": report["summary"]["mirror_coupling"],
            "commit_delay": report["summary"]["commit_delay"],
            "phase_planes": report["summary"]["phase_planes"],
            "auxiliary_stability_counters_per_cell": report["summary"][
                "auxiliary_stability_counters_per_cell"
            ],
            "external_oracle": False,
        },
        "confirmation": [
            {
                "width": row["width"],
                "height": row["height"],
                "seed": row["seed"],
                "trials": row["trials"],
                "s2_recovery_1bit": row["s2_recovery_1bit"],
                "m1_recovery_1bit": row["m1_recovery_1bit"],
                "recovery_gain_vs_s2": row["recovery_gain_vs_s2"],
                "co_corruption_recovery_1bit": row[
                    "co_corruption_recovery_1bit"
                ],
                "co_corruption_gain_vs_s2": row[
                    "co_corruption_gain_vs_s2"
                ],
                "transition_cost_ratio_vs_s2": row[
                    "transition_cost_ratio_vs_s2"
                ],
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

    rendered = json.dumps(
        render_summary(report), indent=2, sort_keys=True
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
