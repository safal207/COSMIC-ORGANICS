"""Diagnostic-only localization of the W4 9x9 confirmation shortfall.

This script does not tune MORPHOS-W4 and does not change any confirmation gate.
It replays the frozen worst confirmation corpus (seed 202608161023) and records
per-trial geometry and transition timing so the next refactor targets the first
meaningful divergence rather than a new amplitude.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from benchmarks.run_w4_confirmation import _load_protocol
from morphos.witness import WitnessLaw
from morphos.witness_selective import SelectiveAuthorityGrid2D

_VALUE = {"A": 0.0, "M": 0.5, "C": 1.0}


def _hamming(a: str, b: str) -> int:
    return sum(left != right for left, right in zip(a, b))


def _position_class(row: int, col: int, width: int, height: int) -> str:
    top_bottom = row in {0, height - 1}
    left_right = col in {0, width - 1}
    if top_bottom and left_right:
        return "corner"
    if top_bottom or left_right:
        return "edge"
    return "interior"


def _trial_features(model: SelectiveAuthorityGrid2D, target: str, index: int) -> dict:
    width = model.config.width
    height = model.config.height
    row, col = divmod(index, width)
    domain = model._domain(index)
    neighbors = model._neighbors(index)
    same_domain = [n for n in neighbors if model._domain(n) == domain]
    cross_domain = [n for n in neighbors if model._domain(n) != domain]
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
    coupling = (
        model.config.anchor_coupling if anchor else model.config.adaptive_coupling
    )
    threshold = (
        model.config.anchor_threshold if anchor else model.config.adaptive_threshold
    )
    neighbor_drive = coupling * weighted_delta
    witness_drive = model.witness_law.witness_drive * direction
    initial_drive = neighbor_drive + witness_drive
    toward_target_drive = initial_drive * direction
    neighbor_same_target = sum(target[n] == target_phase for n in neighbors)
    return {
        "index": index,
        "row": row,
        "col": col,
        "target_phase": target_phase,
        "anchor": anchor,
        "position": _position_class(row, col, width, height),
        "domain": list(domain),
        "domain_local_row": row % model.law.domain_size,
        "domain_local_col": col % model.law.domain_size,
        "same_domain_neighbor_count": len(same_domain),
        "cross_domain_neighbor_count": len(cross_domain),
        "neighbor_count": len(neighbors),
        "neighbor_same_target_count": neighbor_same_target,
        "neighbor_opposite_target_count": len(neighbors) - neighbor_same_target,
        "neighbor_drive": neighbor_drive,
        "initial_toward_target_drive": toward_target_drive,
        "transition_threshold": threshold,
        "initial_threshold_margin": toward_target_drive - threshold,
    }


def _run_trial(target: str, index: int, config, hierarchy, reflective_law, protocol: dict) -> dict:
    model = SelectiveAuthorityGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=reflective_law,
        witness_law=WitnessLaw(
            witness_drive=protocol["witness_drive"],
            commit_delay=protocol["witness_commit_delay"],
        ),
    )
    features = _trial_features(model, target, index)
    _corrupt_all(model, index)

    first_primary_correct_tick = None
    first_exact_recovery_tick = None
    first_fence_release_tick = None
    timeline = []
    for tick in range(1, protocol["retention_horizon"] + 1):
        releases_before = model.fence_release_events
        model.step(0.0)
        exact = model.state_string() == target
        primary_correct = model.states[index] == target[index]
        if primary_correct and first_primary_correct_tick is None:
            first_primary_correct_tick = tick
        if exact and first_exact_recovery_tick is None:
            first_exact_recovery_tick = tick
        if model.fence_release_events > releases_before and first_fence_release_tick is None:
            first_fence_release_tick = tick
        timeline.append(
            {
                "tick": tick,
                "primary": model.states[index],
                "local_mirror": model.local_mirror_states[index],
                "domain_mirror": model.domain_mirror_states[index],
                "system_mirror": model.system_mirror_states[index],
                "fence_active": model.selective_fence_active,
                "residual_hamming": _hamming(model.state_string(), target),
            }
        )

    at8 = timeline[protocol["evaluation_horizon"] - 1]
    at12 = timeline[protocol["retention_horizon"] - 1]
    return {
        **features,
        "success_at_8": at8["residual_hamming"] == 0,
        "success_at_12": at12["residual_hamming"] == 0,
        "target_cell_correct_at_8": at8["primary"] == target[index],
        "residual_hamming_at_8": at8["residual_hamming"],
        "residual_hamming_at_12": at12["residual_hamming"],
        "first_primary_correct_tick": first_primary_correct_tick,
        "first_exact_recovery_tick": first_exact_recovery_tick,
        "first_fence_release_tick": first_fence_release_tick,
        "fence_released_by_8": first_fence_release_tick is not None and first_fence_release_tick <= 8,
        "suppressed_mirror_contributions": model.suppressed_mirror_contributions,
        "preserved_mirror_contributions": model.preserved_mirror_contributions,
        "timeline": timeline,
    }


def _rate(rows: list[dict], key: str) -> float:
    return sum(bool(row[key]) for row in rows) / len(rows) if rows else 0.0


def _group(rows: list[dict], key: str) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return {
        value: {
            "trials": len(group),
            "success_rate_at_8": _rate(group, "success_at_8"),
            "target_cell_correct_rate_at_8": _rate(group, "target_cell_correct_at_8"),
            "mean_initial_threshold_margin": sum(r["initial_threshold_margin"] for r in group) / len(group),
            "mean_residual_hamming_at_8": sum(r["residual_hamming_at_8"] for r in group) / len(group),
        }
        for value, group in sorted(grouped.items())
    }


def run_diagnostic() -> dict:
    protocol = _load_protocol()
    spec = next(
        row for row in protocol["confirmation_corpora"]
        if row["width"] == 9 and row["height"] == 9 and row["seed"] == 202608161023
    )
    base_manifest = _manifest()
    config, hierarchy = _s2_components(base_manifest, 9, 9)
    reflective_law = _m2_law(base_manifest)
    cells = 81
    seeds = _sha_binary_seeds(spec["seed"], spec["samples"], cells)
    targets = _fixed_binary_targets(
        seeds, config, hierarchy, protocol["target_discovery_steps"]
    )[: protocol["max_targets"]]

    rows = []
    for target_index, target in enumerate(targets):
        indices = _noise_indices(spec["seed"], target_index, cells, protocol["trials_per_target"])
        for trial_index, index in enumerate(indices):
            row = _run_trial(target, index, config, hierarchy, reflective_law, protocol)
            row["target_index"] = target_index
            row["trial_index"] = trial_index
            rows.append(row)

    failures = [row for row in rows if not row["success_at_8"]]
    successes = [row for row in rows if row["success_at_8"]]

    def mean(group: list[dict], key: str) -> float | None:
        if not group:
            return None
        return sum(float(row[key]) for row in group) / len(group)

    failure_signatures = Counter(
        (
            "anchor" if row["anchor"] else "adaptive",
            row["position"],
            row["cross_domain_neighbor_count"],
            row["target_phase"],
        )
        for row in failures
    )

    compact_failures = [
        {
            key: row[key]
            for key in (
                "target_index",
                "trial_index",
                "index",
                "row",
                "col",
                "target_phase",
                "anchor",
                "position",
                "domain",
                "domain_local_row",
                "domain_local_col",
                "same_domain_neighbor_count",
                "cross_domain_neighbor_count",
                "neighbor_same_target_count",
                "neighbor_opposite_target_count",
                "initial_toward_target_drive",
                "transition_threshold",
                "initial_threshold_margin",
                "target_cell_correct_at_8",
                "residual_hamming_at_8",
                "first_primary_correct_tick",
                "first_exact_recovery_tick",
                "first_fence_release_tick",
                "suppressed_mirror_contributions",
                "preserved_mirror_contributions",
            )
        }
        for row in failures
    ]

    return {
        "schema": "cosmic-organics/w4-scale-margin-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_confirmation_head": "b528a25f5e3c34fa1983f02219742f8607dca9f2",
        "corpus": spec,
        "trial_count": len(rows),
        "success_count_at_8": len(successes),
        "failure_count_at_8": len(failures),
        "success_rate_at_8": _rate(rows, "success_at_8"),
        "failure_summary": {
            "target_cell_still_wrong_fraction": (
                sum(not row["target_cell_correct_at_8"] for row in failures) / len(failures)
                if failures else 0.0
            ),
            "mean_initial_threshold_margin_failures": mean(failures, "initial_threshold_margin"),
            "mean_initial_threshold_margin_successes": mean(successes, "initial_threshold_margin"),
            "mean_residual_hamming_failures": mean(failures, "residual_hamming_at_8"),
            "failure_signature_counts": [
                {"signature": list(signature), "count": count}
                for signature, count in failure_signatures.most_common()
            ],
        },
        "grouped": {
            "anchor": _group(rows, "anchor"),
            "position": _group(rows, "position"),
            "cross_domain_neighbor_count": _group(rows, "cross_domain_neighbor_count"),
            "target_phase": _group(rows, "target_phase"),
            "domain_local_row": _group(rows, "domain_local_row"),
            "domain_local_col": _group(rows, "domain_local_col"),
            "neighbor_same_target_count": _group(rows, "neighbor_same_target_count"),
        },
        "failures": compact_failures,
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
