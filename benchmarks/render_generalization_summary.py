"""Render the compact, digest-bound Generalization Gate evidence summary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.run_generalization import run_suite


def render_summary() -> dict:
    report = run_suite()
    payload = {
        "multi_bit_summary": report["multi_bit_noise"]["summary"],
        "multi_seed_summary": report["multi_seed"]["summary"],
        "recurrent_summary": report["recurrent_challenge"]["summary"],
        "scale_summary": report["scale"]["summary"],
        "suite_id": report["suite_id"],
        "summary": report["summary"],
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    payload["evidence_digest"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(render_summary(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
