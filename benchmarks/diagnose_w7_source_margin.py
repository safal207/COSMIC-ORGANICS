"""Diagnostic-only source-margin analysis for frozen W7 confirmation residuals.

No scientific mechanism is changed. This replays the same nine W7 confirmation
corpora and asks whether persistent residual failures share a local source-cell
activation/support boundary.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from benchmarks.diagnose_w7_residuals import _run_trial
from benchmarks.probe_witness_persistent import _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.witness import WitnessLaw
from morphos.witness_repair_set import RepairSetAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w7_confirmation_manifest.json")
_VALUE = {"A": 0.0, "M": 0.5, "C": 1.0}


def _source_features(model: RepairSetAuthorityGrid2D, target: str, index: int) -> dict:
    width = model.config.width
    height = model.config.height
    row, col = divmod(index, width)
    domain = model._domain(index)
    neighbors = model._neighbors(index)
    target_phase = target[index]
    wrong_phase = "A" if target_phase == "C" else "C"
    direction = 1.0 if target_phase == "C" else -1.0
    intra_factor = model.law.intra_factor(width, height)
    weighted_delta = sum(
        (intra_factor if model._domain(n) == domain else 1.0)
        * (_VALUE[target[n]] - _VALUE[wrong_phase])
        for n in neighbors
    ) / len(neighbors)
    anchor = model._is_anchor(index)
    coupling = model.config.anchor_coupling if anchor else model.config.adaptive_coupling
    threshold = model.config.anchor_threshold if anchor else model.config.adaptive_threshold
    neighbor_drive = coupling * weighted_delta
    witness_drive = model.witness_law.witness_drive * direction
    toward_target_drive = (neighbor_drive + witness_drive) * direction
    return {
        "source": index,
        "row": row,
        "col": col,
        "anchor": anchor,
        "target_phase": target_phase,
        "neighbor_count": len(neighbors),
        "same_target_neighbors": sum(target[n] == target_phase for n in neighbors),
        "cross_domain_neighbors": sum(model._domain(n) != domain for n in neighbors),
        "domain": list(domain),
        "neighbor_drive": neighbor_drive,
        "witness_drive_toward_target": model.witness_law.witness_drive,
        "initial_toward_target_drive": toward_target_drive,
        "transition_threshold": threshold,
        "initial_threshold_margin": toward_target_drive - threshold,
    }


def run_diagnostic() -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    all_rows = []

    for spec in protocol["confirmation_corpora"]:
        width, height = spec["width"], spec["height"]
        cells = width * height
        config, hierarchy = _s2_components(base, width, height)
        mirror_law = _m2_law(base)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(spec["seed"], spec["samples"], cells),
            config,
            hierarchy,
            protocol["target_discovery_steps"],
        )[: protocol["max_targets"]]
        for target_index, target in enumerate(targets):
            for trial_index, source in enumerate(
                _noise_indices(spec["seed"], target_index, cells, protocol["trials_per_target"])
            ):
                feature_model = RepairSetAuthorityGrid2D(
                    target,
                    config=config,
                    law=hierarchy,
                    reflective_law=mirror_law,
                    witness_law=WitnessLaw(
                        witness_drive=protocol["witness_drive"],
                        commit_delay=protocol["witness_commit_delay"],
                    ),
                )
                features = _source_features(feature_model, target, source)
                outcome = _run_trial(
                    target=target,
                    source=source,
                    config=config,
                    hierarchy=hierarchy,
                    mirror_law=mirror_law,
                    protocol=protocol,
                )
                all_rows.append({
                    **features,
                    "width": width,
                    "height": height,
                    "seed": spec["seed"],
                    "target_index": target_index,
                    "trial_index": trial_index,
                    "success_at_8": outcome["at8"]["exact"],
                    "success_at_12": outcome["at12"]["exact"],
                    "category": outcome["category"],
                    "max_error_count": outcome["max_error_count"],
                    "max_mixed_count": outcome["max_mixed_count"],
                })

    failures = [row for row in all_rows if not row["success_at_12"]]
    successes = [row for row in all_rows if row["success_at_12"]]

    def mean(rows: list[dict], key: str) -> float | None:
        return sum(float(row[key]) for row in rows) / len(rows) if rows else None

    margin_buckets = {
        "negative": lambda x: x < 0,
        "zero_to_0_05": lambda x: 0 <= x < 0.05,
        "0_05_to_0_15": lambda x: 0.05 <= x < 0.15,
        "gte_0_15": lambda x: x >= 0.15,
    }
    bucket_summary = {}
    for label, predicate in margin_buckets.items():
        rows = [row for row in all_rows if predicate(row["initial_threshold_margin"])]
        bucket_summary[label] = {
            "trials": len(rows),
            "persistent_failures": sum(not row["success_at_12"] for row in rows),
            "recovery_at_12": sum(row["success_at_12"] for row in rows) / len(rows) if rows else None,
        }

    return {
        "schema": "cosmic-organics/w7-source-margin-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "confirmation_head_replayed": "77e811ee91a2cc214ca3171f22ade9901a496705",
        "trial_count": len(all_rows),
        "persistent_failure_count": len(failures),
        "persistent_anchor_count": sum(row["anchor"] for row in failures),
        "persistent_adaptive_count": sum(not row["anchor"] for row in failures),
        "persistent_negative_margin_count": sum(row["initial_threshold_margin"] < 0 for row in failures),
        "persistent_nonnegative_margin_count": sum(row["initial_threshold_margin"] >= 0 for row in failures),
        "mean_margin_failures": mean(failures, "initial_threshold_margin"),
        "mean_margin_successes": mean(successes, "initial_threshold_margin"),
        "min_margin_failures": min((row["initial_threshold_margin"] for row in failures), default=None),
        "max_margin_failures": max((row["initial_threshold_margin"] for row in failures), default=None),
        "same_target_neighbor_counts_failures": dict(sorted(Counter(row["same_target_neighbors"] for row in failures).items())),
        "target_phase_counts_failures": dict(sorted(Counter(row["target_phase"] for row in failures).items())),
        "max_error_count_failures": dict(sorted(Counter(row["max_error_count"] for row in failures).items())),
        "margin_buckets": bucket_summary,
        "persistent_failures": failures,
        "interpretation": "measure_local_source_support_before_any_W8_retuning",
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
