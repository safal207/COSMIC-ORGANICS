"""Diagnostic-only scan of repair-induced two-error collateral geometry.

The scan replays the two already-observed W8.2/W8.3 corpus families (864
single-bit common-mode trials total) with frozen W8.2 dynamics. It asks whether
post-source two-binary residuals are constrained to the source's immediate
von-Neumann neighborhood and whether a narrow cancellation decoder based on
verified source coordinate + surviving parity axis would create any false
positive on the observed traces.

No recovery mechanism, coefficient, threshold, parity code, seed, horizon, or
scientific gate is changed.
"""
from __future__ import annotations

import json

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.witness import WitnessLaw
from morphos.witness_executable_margin import ExecutableMarginClosureGrid2D

CORPORA = [
    # Failed W8.2 confirmation family (#37).
    *[{"width": 5, "height": 5, "seed": 202608165000 + i, "samples": 64} for i in (1, 2, 3)],
    *[{"width": 7, "height": 7, "seed": 202608165010 + i, "samples": 64} for i in (1, 2, 3)],
    *[{"width": 9, "height": 9, "seed": 202608165020 + i, "samples": 64} for i in (1, 2, 3)],
    # Failed W8.3 confirmation family (#41).
    *[{"width": 5, "height": 5, "seed": 202608166000 + i, "samples": 64} for i in (1, 2, 3)],
    *[{"width": 7, "height": 7, "seed": 202608166010 + i, "samples": 64} for i in (1, 2, 3)],
    *[{"width": 9, "height": 9, "seed": 202608166020 + i, "samples": 64} for i in (1, 2, 3)],
]

TARGET_DISCOVERY_STEPS = 6
MAX_TARGETS = 8
TRIALS_PER_TARGET = 6
TRACE_HORIZON = 12
WITNESS_DRIVE = 0.25
WITNESS_COMMIT_DELAY = 8


def _errors(model: ExecutableMarginClosureGrid2D, target: str) -> list[int]:
    return [
        i
        for i, (actual, expected) in enumerate(zip(model.state_string(), target))
        if actual != expected
    ]


def _coord(index: int, width: int) -> tuple[int, int]:
    return divmod(index, width)


def _offset(source: int, other: int, width: int) -> tuple[int, int]:
    sr, sc = _coord(source, width)
    rr, rc = _coord(other, width)
    return rr - sr, rc - sc


def _direct_neighbor(source: int, other: int, width: int) -> bool:
    dr, dc = _offset(source, other, width)
    return abs(dr) + abs(dc) == 1


def _classify_pair(source: int, pair: list[int], width: int) -> str:
    offsets = sorted(_offset(source, index, width) for index in pair)
    if all(_direct_neighbor(source, index, width) for index in pair):
        if offsets == [(0, -1), (0, 1)]:
            return "same_row_left_right"
        if offsets == [(-1, 0), (1, 0)]:
            return "same_column_up_down"
        return "orthogonal_neighbors"
    return "nonlocal_or_non_neighbor"


def _verified_source(
    model: ExecutableMarginClosureGrid2D, source: int, target: str
) -> bool:
    return (
        model.selective_fence_active
        and len(model.protected_targets) == 1
        and model.protected_targets.get(source) == target[source]
        and model.states[source] == target[source]
    )


def _candidate_from_cancelled_axis(
    model: ExecutableMarginClosureGrid2D, source: int
) -> tuple[list[int] | None, str | None]:
    """Return the narrow locality candidate, if its observable predicate holds.

    Row-cancellation: no bad rows, exactly two bad columns. Repair history supplies
    the verified source row. The candidate is those two columns on source row.

    Column-cancellation is symmetric.

    To keep the proposed primitive fail-closed, both inferred cells must be
    immediate von-Neumann neighbors of the verified source, binary, unprotected,
    and their virtual flip must restore the full committed parity witness.
    """
    bad_rows, bad_columns = model.syndrome()
    sr, sc = _coord(source, model.config.width)

    if len(bad_rows) == 0 and len(bad_columns) == 2:
        candidate = sorted(sr * model.config.width + col for col in bad_columns)
        kind = "same_row_cancelled"
    elif len(bad_rows) == 2 and len(bad_columns) == 0:
        candidate = sorted(row * model.config.width + sc for row in bad_rows)
        kind = "same_column_cancelled"
    else:
        return None, None

    if source in candidate:
        return None, None
    if any(index in model.protected_targets for index in candidate):
        return None, None
    if any(model.states[index] not in ("A", "C") for index in candidate):
        return None, None
    if not all(_direct_neighbor(source, index, model.config.width) for index in candidate):
        return None, None

    virtual = model.states.copy()
    for index in candidate:
        virtual[index] = "C" if virtual[index] == "A" else "A"
    rows, columns = model._parity("".join(virtual))
    if rows != model.row_parity or columns != model.column_parity:
        return None, None
    return candidate, kind


def _scan_trial(
    *,
    target: str,
    source: int,
    target_index: int,
    trial_index: int,
    corpus: dict,
    config,
    hierarchy,
    mirror_law,
) -> tuple[list[dict], list[dict]]:
    model = ExecutableMarginClosureGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(
            witness_drive=WITNESS_DRIVE,
            commit_delay=WITNESS_COMMIT_DELAY,
        ),
    )
    _corrupt_all(model, source)
    pair_states = []
    candidate_states = []
    seen_pair_signature = set()
    seen_candidate_signature = set()

    for tick in range(1, TRACE_HORIZON + 1):
        model.step(0.0)
        actual_errors = _errors(model, target)
        verified = _verified_source(model, source, target)

        if (
            verified
            and len(actual_errors) == 2
            and source not in actual_errors
            and all(model.states[index] in ("A", "C") for index in actual_errors)
        ):
            signature = tuple(actual_errors)
            if signature not in seen_pair_signature:
                seen_pair_signature.add(signature)
                pair_states.append(
                    {
                        "width": corpus["width"],
                        "height": corpus["height"],
                        "seed": corpus["seed"],
                        "target_index": target_index,
                        "trial_index": trial_index,
                        "source": source,
                        "tick": tick,
                        "errors": actual_errors,
                        "offsets": [list(_offset(source, index, corpus["width"])) for index in actual_errors],
                        "geometry": _classify_pair(source, actual_errors, corpus["width"]),
                        "both_direct_neighbors": all(
                            _direct_neighbor(source, index, corpus["width"])
                            for index in actual_errors
                        ),
                        "syndrome_rows": list(model.syndrome()[0]),
                        "syndrome_columns": list(model.syndrome()[1]),
                    }
                )

        if verified:
            candidate, kind = _candidate_from_cancelled_axis(model, source)
            if candidate is not None:
                signature = (tuple(candidate), kind)
                if signature not in seen_candidate_signature:
                    seen_candidate_signature.add(signature)
                    candidate_states.append(
                        {
                            "width": corpus["width"],
                            "height": corpus["height"],
                            "seed": corpus["seed"],
                            "target_index": target_index,
                            "trial_index": trial_index,
                            "source": source,
                            "tick": tick,
                            "candidate": candidate,
                            "kind": kind,
                            "actual_errors": actual_errors,
                            "candidate_equals_actual_errors": candidate == actual_errors,
                            "actual_error_count": len(actual_errors),
                            "syndrome_rows": list(model.syndrome()[0]),
                            "syndrome_columns": list(model.syndrome()[1]),
                        }
                    )

    return pair_states, candidate_states


def main() -> None:
    base = _manifest()
    all_pair_states = []
    all_candidate_states = []
    total_trials = 0

    for corpus in CORPORA:
        width, height = corpus["width"], corpus["height"]
        cells = width * height
        config, hierarchy = _s2_components(base, width, height)
        mirror_law = _m2_law(base)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(corpus["seed"], corpus["samples"], cells),
            config,
            hierarchy,
            TARGET_DISCOVERY_STEPS,
        )[:MAX_TARGETS]
        for target_index, target in enumerate(targets):
            indices = _noise_indices(
                corpus["seed"], target_index, cells, TRIALS_PER_TARGET
            )
            for trial_index, source in enumerate(indices):
                total_trials += 1
                pair_states, candidate_states = _scan_trial(
                    target=target,
                    source=source,
                    target_index=target_index,
                    trial_index=trial_index,
                    corpus=corpus,
                    config=config,
                    hierarchy=hierarchy,
                    mirror_law=mirror_law,
                )
                all_pair_states.extend(pair_states)
                all_candidate_states.extend(candidate_states)

    geometry_counts: dict[str, int] = {}
    for row in all_pair_states:
        geometry_counts[row["geometry"]] = geometry_counts.get(row["geometry"], 0) + 1

    false_positive_candidates = [
        row for row in all_candidate_states if not row["candidate_equals_actual_errors"]
    ]
    true_positive_candidates = [
        row for row in all_candidate_states if row["candidate_equals_actual_errors"]
    ]
    nonlocal_pairs = [
        row for row in all_pair_states if not row["both_direct_neighbors"]
    ]

    hypothesis_supported = (
        len(all_pair_states) >= 3
        and not nonlocal_pairs
        and len(true_positive_candidates) >= 1
        and not false_positive_candidates
    )

    report = {
        "schema": "cosmic-organics/w83-collateral-geometry-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "observed_corpus_families": ["202608165", "202608166"],
        "trials": total_trials,
        "pair_states": all_pair_states,
        "cancellation_decoder_candidate_states": all_candidate_states,
        "false_positive_candidates": false_positive_candidates,
        "summary": {
            "pair_state_count": len(all_pair_states),
            "geometry_counts": geometry_counts,
            "pair_states_with_both_direct_neighbors": sum(
                row["both_direct_neighbors"] for row in all_pair_states
            ),
            "nonlocal_pair_states": len(nonlocal_pairs),
            "cancellation_candidate_activations": len(all_candidate_states),
            "cancellation_candidate_true_positives": len(true_positive_candidates),
            "cancellation_candidate_false_positives": len(false_positive_candidates),
            "hypothesis_supported_on_observed_evidence": hypothesis_supported,
        },
        "decision_contract": (
            "a W8.4 causal-locality experiment is admissible only if every observed "
            "post-source two-binary residual is made of direct von-Neumann source "
            "neighbors and the narrow cancelled-axis candidate produces at least one "
            "true positive with zero false positives across all scanned observed traces"
        ),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if not hypothesis_supported:
        raise SystemExit("causal-locality hypothesis not supported on observed evidence")


if __name__ == "__main__":
    main()
