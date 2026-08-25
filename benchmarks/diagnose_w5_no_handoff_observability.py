"""Microdiagnose why frozen W5 collateral failures never become handoff-eligible.

Diagnostic only. Replays the 10 no-handoff cases from W5 confirmation and
separates global mixed-phase blindness, multi-error ambiguity, premature
witness recommit, and binary-but-ambiguous states.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

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
from morphos.witness_handoff import HandoffAuthorityGrid2D
from morphos.witness_selective import SelectiveAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w5_confirmation_manifest.json")


def _errors(model, target: str) -> list[int]:
    return [
        i
        for i, (actual, expected) in enumerate(zip(model.states, target))
        if actual != expected
    ]


def _run_trace(target, source, config, hierarchy, mirror_law, protocol):
    model = HandoffAuthorityGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(
            witness_drive=protocol["witness_drive"],
            commit_delay=protocol["witness_commit_delay"],
        ),
    )
    initial_witness = model.witness_signature()
    _corrupt_all(model, source)
    trace = []
    source_correct_seen = False
    for tick in range(1, protocol["retention_horizon"] + 1):
        model.step(0.0)
        errors = _errors(model, target)
        source_correct = source not in errors
        source_correct_seen = source_correct_seen or source_correct
        binary = all(value in ("A", "C") for value in model.states)
        syndrome = model.syndrome()
        localized = model.localized_error_index()
        trace.append(
            {
                "tick": tick,
                "errors": errors,
                "error_phases": {str(i): model.states[i] for i in errors},
                "source_correct": source_correct,
                "after_source_correct": source_correct_seen,
                "mixed_indices": [
                    i for i, value in enumerate(model.states) if value == "M"
                ],
                "binary": binary,
                "syndrome_rows": list(syndrome[0]),
                "syndrome_columns": list(syndrome[1]),
                "localized": localized,
                "latched_index": model.latched_index,
                "handoff_events": model.handoff_events,
                "witness_commit_events": model.witness_commit_events,
                "witness_changed": model.witness_signature() != initial_witness,
                "witness_stable_count": model.witness_stable_count,
            }
        )
    return model, initial_witness, trace


def _classify(trace: list[dict]) -> tuple[str, dict]:
    post = [row for row in trace if row["after_source_correct"] and row["errors"]]
    if not post:
        return "not_applicable", {}

    witness_changed = any(row["witness_changed"] for row in post)
    witness_commit = any(row["witness_commit_events"] > 0 for row in post)
    binary_rows = [row for row in post if row["binary"]]
    mixed_rows = [row for row in post if not row["binary"]]
    unique_other_rows = [
        row
        for row in post
        if row["localized"] is not None and row["localized"] not in row["errors"][:0]
    ]
    # The caller has already selected no-handoff cases; any localized different
    # owner would have triggered handoff. Keep this metric only as a guard.
    del unique_other_rows

    if witness_changed or witness_commit:
        category = "witness_recommitted"
    elif not binary_rows:
        category = "mixed_state_unobservable"
    else:
        multi_binary = [row for row in binary_rows if len(row["errors"]) > 1]
        ambiguous_binary = [
            row
            for row in binary_rows
            if row["localized"] is None and row["errors"]
        ]
        if multi_binary:
            category = "multi_error_ambiguous"
        elif ambiguous_binary:
            category = "binary_but_ambiguous"
        elif mixed_rows:
            category = "mixed_state_unobservable"
        else:
            category = "other"

    detail = {
        "post_source_error_ticks": len(post),
        "mixed_blind_ticks": len(mixed_rows),
        "binary_observable_ticks": len(binary_rows),
        "witness_changed": witness_changed,
        "witness_commit_seen": witness_commit,
        "max_error_count": max(len(row["errors"]) for row in post),
        "residual_phases_at_8": next(
            (row["error_phases"] for row in trace if row["tick"] == 8), {}
        ),
        "residual_phases_at_12": next(
            (row["error_phases"] for row in trace if row["tick"] == 12), {}
        ),
        "syndrome_at_8": next(
            (
                [row["syndrome_rows"], row["syndrome_columns"]]
                for row in trace
                if row["tick"] == 8
            ),
            [[], []],
        ),
        "syndrome_at_12": next(
            (
                [row["syndrome_rows"], row["syndrome_columns"]]
                for row in trace
                if row["tick"] == 12
            ),
            [[], []],
        ),
    }
    return category, detail


def run_diagnostic() -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    rows = []

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
            indices = _noise_indices(
                spec["seed"],
                target_index,
                cells,
                protocol["trials_per_target"],
            )
            for trial_index, source in enumerate(indices):
                w4 = _run(
                    SelectiveAuthorityGrid2D,
                    target,
                    [source],
                    config,
                    hierarchy,
                    mirror_law,
                    protocol["evaluation_horizon"],
                    witness_drive=protocol["witness_drive"],
                    witness_commit_delay=protocol["witness_commit_delay"],
                )
                if w4.state_string() == target or w4.states[source] != target[source]:
                    continue

                model, initial_witness, trace = _run_trace(
                    target,
                    source,
                    config,
                    hierarchy,
                    mirror_law,
                    protocol,
                )
                if model.handoff_events > 0:
                    continue
                if not any(row["errors"] for row in trace[7:8]):
                    continue

                category, detail = _classify(trace)
                rows.append(
                    {
                        "width": width,
                        "height": height,
                        "seed": spec["seed"],
                        "target_index": target_index,
                        "trial_index": trial_index,
                        "source": source,
                        "source_anchor": model._is_anchor(source),
                        "category": category,
                        "initial_witness": [list(initial_witness[0]), list(initial_witness[1])],
                        "final_witness": [
                            list(model.witness_signature()[0]),
                            list(model.witness_signature()[1]),
                        ],
                        **detail,
                        "trace": trace,
                    }
                )

    counts = Counter(row["category"] for row in rows)
    by_size = {}
    for size in sorted({f'{row["width"]}x{row["height"]}' for row in rows}):
        size_rows = [row for row in rows if f'{row["width"]}x{row["height"]}' == size]
        by_size[size] = dict(sorted(Counter(row["category"] for row in size_rows).items()))

    return {
        "schema": "cosmic-organics/w5-no-handoff-observability-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_confirmation_head": "5436f9bdc8ba5dc47587c5360914555e0af3bc84",
        "case_count": len(rows),
        "category_counts": dict(sorted(counts.items())),
        "by_size": by_size,
        "cases": rows,
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
