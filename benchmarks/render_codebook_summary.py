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


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def render_summary(report: dict | None = None) -> dict:
    if report is None:
        report = run_suite()

    large = [item for item in report["corpora"] if item["width"] > 5]
    five = [item for item in report["corpora"] if item["width"] == 5]
    large_model_recovery = {
        model: _mean([
            item["models"][model]["one_bit"]["dynamic_recovery"]
            for item in large
        ])
        for model in ("majority_ca", "s1", "s2")
    }
    s2_large_unique = _mean([
        item["models"]["s2"]["one_bit"]["unique_nearest_fraction"]
        for item in large
    ])
    s2_large_recovery = large_model_recovery["s2"]
    s2_five_collision_failure_share = _mean([
        item["models"]["s2"]["one_bit"]["hard_collision_share_of_failures"]
        for item in five
    ])

    s2_corpora = []
    for item in report["corpora"]:
        model = item["models"]["s2"]
        geometry = model["geometry"]
        one_bit = model["one_bit"]
        s2_corpora.append({
            "width": item["width"],
            "height": item["height"],
            "seed": item["seed"],
            "samples": item["samples"],
            "codebook_size": geometry["codebook_size"],
            "min_distance": geometry["min_distance"],
            "mean_nearest_distance": geometry["mean_nearest_distance"],
            "distance1_pair_count": geometry["distance1_pair_count"],
            "distance2_pair_count": geometry["distance2_pair_count"],
            "distance3_single_bit_guarantee": geometry[
                "distance3_single_bit_guarantee"
            ],
            "unique_nearest_fraction": one_bit["unique_nearest_fraction"],
            "direct_codeword_collision_fraction": one_bit[
                "direct_codeword_collision_fraction"
            ],
            "dynamic_recovery": one_bit["dynamic_recovery"],
            "dynamic_recovery_on_direct_collision": one_bit[
                "dynamic_recovery_on_direct_collision"
            ],
            "hard_collision_share_of_failures": one_bit[
                "hard_collision_share_of_failures"
            ],
        })

    payload = {
        "schema_version": "cosmic-organics/codebook-summary-0.2",
        "suite_id": report["suite_id"],
        "selection_rule": report["selection_rule"],
        "portable_identity_scope": "quantized_s2_codebook_diagnostic_summary",
        "quantization_decimals": QUANTIZATION_DECIMALS,
        "scientific_boundary": report["scientific_boundary"],
        "s2_corpora": s2_corpora,
        "large_scale_model_mean_dynamic_recovery": large_model_recovery,
        "s2_large_scale_unique_identification_minus_dynamic_recovery": (
            s2_large_unique - s2_large_recovery
        ),
        "s2_5x5_mean_hard_collision_share_of_failures": (
            s2_five_collision_failure_share
        ),
        "large_scale_geometry_ambiguity_explains_recovery_collapse": False,
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
