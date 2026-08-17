"""Diagnostic-only global false-positive scan for a prospective W8.5 solver.

The scan replays all already-observed seed families 202608165..202608168:
36 corpora / 1728 single-bit common-mode trials, through tick 12, using frozen
W8.4 dynamics. It evaluates a runtime-shaped candidate without changing the
model: one active repair transaction, exactly one verified protected source,
exactly two current M cells, unique GF(2) endpoint solution, and full virtual
committed-parity validation.

Frozen target truth is used only to label diagnostic false positives. A future
runtime decoder would not receive target truth.
"""
from __future__ import annotations

import json

from benchmarks.diagnose_w84_multierasure_solvability import (
    _bit,
    _equations,
    _gf2_solve,
    _virtual_parity_ok,
)
from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.witness import WitnessLaw
from morphos.witness_causal_locality import CausalLocalityAuthorityGrid2D

FAMILIES = (202608165, 202608166, 202608167, 202608168)
SAMPLES = 64
MAX_TARGETS = 8
TRIALS_PER_TARGET = 6
TRACE_HORIZON = 12


def _corpora() -> list[dict]:
    rows = []
    for family in FAMILIES:
        for size, suffix_base in ((5, 0), (7, 10), (9, 20)):
            for offset in (1, 2, 3):
                rows.append(
                    {
                        "width": size,
                        "height": size,
                        "seed": family * 1000 + suffix_base + offset,
                        "samples": SAMPLES,
                    }
                )
    return rows


def _wrong_binary(model, target: str, m_indices: list[int]) -> list[int]:
    m_set = set(m_indices)
    return [
        index
        for index, (actual, expected) in enumerate(zip(model.states, target))
        if index not in m_set
        and actual in ("A", "C")
        and actual != expected
    ]


def _candidate(
    model: CausalLocalityAuthorityGrid2D,
    *,
    source: int,
    target: str,
) -> dict | None:
    if (
        not model.selective_fence_active
        or model.witness_law.witness_drive <= 0
        or len(model.protected_targets) != 1
        or model.latched_index != source
        or model.protected_targets.get(source) != target[source]
        or model.states[source] != target[source]
    ):
        return None

    m_indices = [index for index, phase in enumerate(model.states) if phase == "M"]
    if len(m_indices) != 2:
        return None
    if any(index in model.protected_targets for index in m_indices):
        return None

    matrix, rhs = _equations(model, m_indices)
    solved = _gf2_solve(matrix, rhs, len(m_indices))
    if solved["status"] != "unique_solution":
        return None
    bits = solved["solution"]
    if bits is None or not _virtual_parity_ok(model, m_indices, bits):
        return None

    target_bits = [_bit(target[index]) for index in m_indices]
    wrong_binary = _wrong_binary(model, target, m_indices)
    return {
        "m_indices": m_indices,
        "solution_bits": bits,
        "target_bits": target_bits,
        "solution_matches_target": bits == target_bits,
        "wrong_binary_indices": wrong_binary,
        "wrong_binary_count": len(wrong_binary),
        "safe_by_frozen_truth": bits == target_bits and not wrong_binary,
        "rank": solved["rank"],
        "variables": solved["variables"],
    }


def main() -> None:
    base = _manifest()
    candidate_states = []
    candidate_trial_keys = set()
    safe_trial_keys = set()
    false_positive_trial_keys = set()
    total_trials = 0
    total_ticks = 0

    for corpus in _corpora():
        width, height = corpus["width"], corpus["height"]
        cells = width * height
        config, hierarchy = _s2_components(base, width, height)
        mirror_law = _m2_law(base)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(corpus["seed"], corpus["samples"], cells),
            config,
            hierarchy,
            6,
        )[:MAX_TARGETS]

        for target_index, target in enumerate(targets):
            sources = _noise_indices(
                corpus["seed"], target_index, cells, TRIALS_PER_TARGET
            )
            for trial_index, source in enumerate(sources):
                total_trials += 1
                key = (
                    width,
                    height,
                    corpus["seed"],
                    target_index,
                    trial_index,
                    source,
                )
                model = CausalLocalityAuthorityGrid2D(
                    target,
                    config=config,
                    law=hierarchy,
                    reflective_law=mirror_law,
                    witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
                )
                _corrupt_all(model, source)

                for tick in range(1, TRACE_HORIZON + 1):
                    total_ticks += 1
                    model.step(0.0)
                    candidate = _candidate(model, source=source, target=target)
                    if candidate is None:
                        continue
                    candidate_trial_keys.add(key)
                    if candidate["safe_by_frozen_truth"]:
                        safe_trial_keys.add(key)
                    else:
                        false_positive_trial_keys.add(key)
                    candidate_states.append(
                        {
                            "width": width,
                            "height": height,
                            "seed": corpus["seed"],
                            "target_index": target_index,
                            "trial_index": trial_index,
                            "source": source,
                            "tick": tick,
                            **candidate,
                        }
                    )

    false_positive_states = [
        row for row in candidate_states if not row["safe_by_frozen_truth"]
    ]
    wrong_endpoint_states = [
        row for row in candidate_states if not row["solution_matches_target"]
    ]
    hidden_wrong_binary_states = [
        row for row in candidate_states if row["wrong_binary_count"] > 0
    ]

    known_persistent_keys = {
        (7, 7, 202608167012, 3, 5, 19),
        (7, 7, 202608167013, 1, 4, 33),
    }
    known_late_keys = {
        (7, 7, 202608167013, 1, 5, 32),
        (9, 9, 202608167023, 3, 1, 70),
    }

    summary = {
        "corpora": len(_corpora()),
        "trials": total_trials,
        "ticks_scanned": total_ticks,
        "candidate_states": len(candidate_states),
        "candidate_trials": len(candidate_trial_keys),
        "safe_candidate_trials": len(safe_trial_keys),
        "false_positive_candidate_states": len(false_positive_states),
        "false_positive_candidate_trials": len(false_positive_trial_keys),
        "wrong_endpoint_candidate_states": len(wrong_endpoint_states),
        "candidate_states_with_hidden_wrong_binary": len(hidden_wrong_binary_states),
        "known_persistent_trials_with_candidate": len(
            known_persistent_keys & candidate_trial_keys
        ),
        "known_late_trials_with_candidate": len(known_late_keys & candidate_trial_keys),
        "all_candidate_states_safe_by_frozen_truth": not false_positive_states,
    }

    report = {
        "schema": "cosmic-organics/w84-multierasure-global-scan-0.1",
        "diagnostic_only_no_retuning": True,
        "observed_families": list(FAMILIES),
        "runtime_shaped_candidate": (
            "active one-source repair transaction + verified source + exactly two M "
            "+ unique GF(2) solution + complete virtual committed-parity replay"
        ),
        "summary": summary,
        "false_positive_states": false_positive_states,
        "candidate_states": candidate_states,
        "decision_contract": (
            "direct W8.5 multi-M solver development is admissible only if the global "
            "observed scan contains at least one candidate, covers both known persistent "
            "trajectories, and contains zero wrong-endpoint or hidden-wrong-binary "
            "candidate activations"
        ),
    }
    print(json.dumps(report, indent=2, sort_keys=True))

    if not (
        summary["candidate_trials"] > 0
        and summary["known_persistent_trials_with_candidate"] == 2
        and summary["wrong_endpoint_candidate_states"] == 0
        and summary["candidate_states_with_hidden_wrong_binary"] == 0
        and summary["false_positive_candidate_states"] == 0
    ):
        raise SystemExit("global multi-M solver candidate safety contract failed")


if __name__ == "__main__":
    main()
