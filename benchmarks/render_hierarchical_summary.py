"""Render the compact, digest-bound MORPHOS-S2 evidence summary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.run_hierarchical import run_suite


def render_summary() -> dict:
    report = run_suite()
    by_exponent = {
        row["hierarchy_exponent"]: row
        for row in report["discovery"]
    }
    payload = {
        "schema_version": "cosmic-organics/hierarchical-summary-0.1",
        "suite_id": report["suite_id"],
        "full_result_digest": report["result_digest"],
        "selection_rule": report["selection_rule"],
        "discovery_boundary": {
            "selected": by_exponent[0.06],
            "next_rejected": by_exponent[0.07],
        },
        "summary": report["summary"],
    }
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(
        render_summary(),
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
