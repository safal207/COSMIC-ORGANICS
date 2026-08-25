"""Render a portable 9-decimal scientific summary for W5 confirmation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _q(value):
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, list):
        return [_q(item) for item in value]
    if isinstance(value, dict):
        return {key: _q(item) for key, item in value.items()}
    return value


def render(report: dict) -> dict:
    body = {
        "schema": "cosmic-organics/w5-confirmation-summary-0.1",
        "portable_identity_scope": "quantized_scientific_summary",
        "quantization_decimals": 9,
        "frozen_from_head": report["frozen_from_head"],
        "confirmation_only_no_retuning": report["confirmation_only_no_retuning"],
        "criteria": report["criteria"],
        "rows": report["rows"],
        "summary": report["summary"],
        "passes": report["passes"],
        "scope_boundary": report["scope_boundary"],
    }
    body = _q(body)
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    body["portable_evidence_digest"] = hashlib.sha256(canonical).hexdigest()
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    args.output.write_text(json.dumps(render(report), indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
