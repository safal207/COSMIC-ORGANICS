"""Render portable MORPHOS-S3 attractor-codebook evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.run_codebook_geometry import run_suite

QUANTIZATION_DECIMALS = 9


def _quantize(value):
    if isinstance(value, float):
        return round(value, QUANTIZATION_DECIMALS)
    if isinstance(value, list):
        return [_quantize(item) for item in value]
    if isinstance(value, dict):
        return {key: _quantize(item) for key, item in value.items()}
    return value


def _compact_model(model: dict) -> dict:
    geometry = model["geometry"]
    one_bit = model["one_bit"]
    return {
        "codebook_size": geometry["codebook_size"],
        "min_distance": geometry["min_distance"],
        "mean_nearest_distance": geometry["mean_nearest_distance"],
        "distance1_pair_count": geometry["distance1_pair_count"],
        "distance2_pair_count": geometry["distance2_pair_count"],
        "distance3_single_bit_guarantee": geometry[
            "distance3_single_bit_guarantee"
        ],
        "trials": one_bit["trials"],
        "unique_nearest_fraction": one_bit["unique_nearest_fraction"],
        "nearest_ambiguity_fraction": one_bit[
            "nearest_ambiguity_fraction"
        ],
        "direct_codeword_collision_fraction": one_bit[
            "direct_codeword_collision_fraction"
        ],
        "dynamic_recovery": one_bit["dynamic_recovery"],
        "dynamic_recovery_on_unique_nearest": one_bit[
            "dynamic_recovery_on_unique_nearest"
        ],
        "dynamic_recovery_on_ambiguous": one_bit[
            "dynamic_recovery_on_ambiguous"
        ],
        "dynamic_recovery_on_direct_collision": one_bit[
            "dynamic_recovery_on_direct_collision"
        ],
        "hard_collision_share_of_failures": one_bit[
            "hard_collision_share_of_failures"
        ],
    }


def render_summary(report: dict | None = None) -> dict:
    if report is None:
        report = run_suite()
    payload = {
        "schema_version": "cosmic-organics/codebook-summary-0.1",
        "suite_id": report["suite_id"],
        "selection_rule": report["selection_rule"],
        "portable_identity_scope": "quantized_sampled_codebook_geometry",
        "quantization_decimals": QUANTIZATION_DECIMALS,
        "scientific_boundary": report["scientific_boundary"],
        "corpora": [
            {
                "width": item["width"],
                "height": item["height"],
                "seed": item["seed"],
                "samples": item["samples"],
                "models": {
                    name: _compact_model(model)
                    for name, model in item["models"].items()
                },
            }
            for item in report["corpora"]
        ],
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
