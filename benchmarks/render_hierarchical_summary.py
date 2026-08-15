"""Render the portable, digest-bound MORPHOS-S2 evidence summary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.run_hierarchical import run_suite

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
    by_exponent = {
        row["hierarchy_exponent"]: row
        for row in report["discovery"]
    }
    payload = {
        "schema_version": "cosmic-organics/hierarchical-summary-0.2",
        "suite_id": report["suite_id"],
        "selection_rule": report["selection_rule"],
        "portable_identity_scope": "quantized_scientific_summary",
        "quantization_decimals": QUANTIZATION_DECIMALS,
        "discovery_boundary": {
            "selected": by_exponent[0.06],
            "next_rejected": by_exponent[0.07],
        },
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
        render_summary(report),
        indent=2,
        sort_keys=True,
    ) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
