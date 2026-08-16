"""Split W6 post-endpoint failures into rebound vs collateral propagation.

Diagnostic only. Replays exactly the nine frozen W5 mixed-erasure cases under
unchanged W6 and records the error set after the erasure-owned cell first
reaches its independently inferred endpoint.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from benchmarks.probe_witness_erasure import _is_diagnosed_mixed_erasure
from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from benchmarks.run_w4_confirmation import _run
from morphos.witness import WitnessLaw
from morphos.witness_erasure import ErasureAwareAuthorityGrid2D
from morphos.witness_handoff import HandoffAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w6_erasure_manifest.json")


def _errors(model, target: str) -> list[int]:
    return [i for i, (actual, expected) in enumerate(zip(model.states, target)) if actual != expected]


def _relation(model, left: int, right: int) -> dict:
    width = model.config.width
    lr, lc = divmod(left, width)
    rr, rc = divmod(right, width)
    return {
        "manhattan": abs(lr - rr) + abs(lc - rc),
        "direct_neighbor": right in model._neighbors(left),
        "same_domain": model._domain(left) == model._domain(right),
    }


def _trace(target: str, source: int, config, hierarchy, mirror_law, spec: dict) -> dict:
    model = ErasureAwareAuthorityGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(
            witness_drive=spec["witness_drive"],
            commit_delay=spec["witness_commit_delay"],
        ),
    )
    _corrupt_all(model, source)

    erasure_owner = None
    erasure_handoff_tick = None
    first_owner_endpoint_tick = None
    rows = []
    for tick in range(1, spec["retention_horizon"] + 1):
        erasure_before = model.erasure_handoff_events
        model.step(0.0)
        if model.erasure_handoff_events > erasure_before and erasure_owner is None:
            erasure_owner = model.handoff_history[-1][1]
            erasure_handoff_tick = tick
        owner_phase = model.states[erasure_owner] if erasure_owner is not None else None
        owner_target = target[erasure_owner] if erasure_owner is not None else None
        if (
            erasure_owner is not None
            and owner_phase == owner_target
            and first_owner_endpoint_tick is None
        ):
            first_owner_endpoint_tick = tick
        errors = _errors(model, target)
        rows.append(
            {
                "tick": tick,
                "errors": errors,
                "error_phases": {str(i): model.states[i] for i in errors},
                "owner_phase": owner_phase,
                "owner_at_target": (
                    erasure_owner is not None and owner_phase == owner_target
                ),
                "latched_index": model.latched_index,
                "latched_target": model.latched_target,
                "handoff_events": model.handoff_events,
                "erasure_handoff_events": model.erasure_handoff_events,
                "handoff_history": [list(pair) for pair in model.handoff_history],
                "protected_targets": {str(k): v for k, v in model.protected_targets.items()},
                "fence_active": model.selective_fence_active,
            }
        )

    post_endpoint = [
        row for row in rows
        if first_owner_endpoint_tick is not None and row["tick"] >= first_owner_endpoint_tick
    ]
    owner_rebound_ticks = [
        row["tick"] for row in post_endpoint if not row["owner_at_target"]
    ]
    collateral_rows = [
        row for row in post_endpoint
        if row["owner_at_target"] and any(i != erasure_owner for i in row["errors"])
    ]
    distinct_collateral = sorted({
        i
        for row in collateral_rows
        for i in row["errors"]
        if i != erasure_owner
    })

    if owner_rebound_ticks:
        category = "owner_rebound"
    elif distinct_collateral:
        category = "owner_stable_collateral"
    elif any(row["errors"] for row in post_endpoint):
        category = "owner_endpoint_but_self_error_recorded"
    else:
        category = "exact_recovery"

    return {
        "source": source,
        "erasure_owner": erasure_owner,
        "erasure_handoff_tick": erasure_handoff_tick,
        "first_owner_endpoint_tick": first_owner_endpoint_tick,
        "category": category,
        "owner_rebound_ticks": owner_rebound_ticks,
        "distinct_collateral_errors": distinct_collateral,
        "collateral_relations_to_owner": [
            {"index": i, **_relation(model, erasure_owner, i)}
            for i in distinct_collateral
        ] if erasure_owner is not None else [],
        "collateral_relations_to_source": [
            {"index": i, **_relation(model, source, i)}
            for i in distinct_collateral
        ],
        "handoff_history_final": [list(pair) for pair in model.handoff_history],
        "exact_at_8": not rows[spec["evaluation_horizon"] - 1]["errors"],
        "exact_at_12": not rows[spec["retention_horizon"] - 1]["errors"],
        "errors_at_8": rows[spec["evaluation_horizon"] - 1]["errors"],
        "errors_at_12": rows[spec["retention_horizon"] - 1]["errors"],
        "timeline": rows,
    }


def run_diagnostic() -> dict:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    cases = []
    for corpus in spec["corpora"]:
        width, height = corpus["width"], corpus["height"]
        cells = width * height
        config, hierarchy = _s2_components(base, width, height)
        mirror_law = _m2_law(base)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(corpus["seed"], corpus["samples"], cells),
            config,
            hierarchy,
            spec["target_discovery_steps"],
        )[: spec["max_targets"]]
        for target_index, target in enumerate(targets):
            indices = _noise_indices(corpus["seed"], target_index, cells, spec["trials_per_target"])
            for trial_index, source in enumerate(indices):
                kwargs = dict(
                    target=target,
                    indices=[source],
                    config=config,
                    hierarchy=hierarchy,
                    m2_law=mirror_law,
                    witness_drive=spec["witness_drive"],
                    witness_commit_delay=spec["witness_commit_delay"],
                )
                w5_8 = _run(HandoffAuthorityGrid2D, horizon=spec["evaluation_horizon"], **kwargs)
                w5_12 = _run(HandoffAuthorityGrid2D, horizon=spec["retention_horizon"], **kwargs)
                if not _is_diagnosed_mixed_erasure(w5_8, w5_12, target, source):
                    continue
                row = _trace(target, source, config, hierarchy, mirror_law, spec)
                row.update(
                    {
                        "width": width,
                        "height": height,
                        "seed": corpus["seed"],
                        "target_index": target_index,
                        "trial_index": trial_index,
                    }
                )
                cases.append(row)

    counts = Counter(case["category"] for case in cases)
    compact_cases = [
        {
            "size": f'{case["width"]}x{case["height"]}',
            "seed": case["seed"],
            "target_index": case["target_index"],
            "trial_index": case["trial_index"],
            "source": case["source"],
            "erasure_owner": case["erasure_owner"],
            "erasure_handoff_tick": case["erasure_handoff_tick"],
            "first_owner_endpoint_tick": case["first_owner_endpoint_tick"],
            "category": case["category"],
            "owner_rebound_ticks": case["owner_rebound_ticks"],
            "distinct_collateral_errors": case["distinct_collateral_errors"],
            "collateral_relations_to_owner": case["collateral_relations_to_owner"],
            "handoff_history_final": case["handoff_history_final"],
            "errors_at_8": case["errors_at_8"],
            "errors_at_12": case["errors_at_12"],
        }
        for case in cases
    ]
    return {
        "schema": "cosmic-organics/w6-post-endpoint-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "case_count": len(cases),
        "category_counts": dict(sorted(counts.items())),
        "owner_rebound_case_count": sum(bool(c["owner_rebound_ticks"]) for c in cases),
        "owner_stable_collateral_case_count": sum(c["category"] == "owner_stable_collateral" for c in cases),
        "cases_with_additional_handoff_after_erasure": sum(len(c["handoff_history_final"]) > 2 for c in cases),
        "cases": compact_cases,
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
