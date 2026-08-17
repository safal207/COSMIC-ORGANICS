"""Diagnostic-only GF(2) solvability analysis for frozen multi-M trajectories.

Known `M` locations are treated as erasures whose future A/C endpoint bits are
unknown. Existing committed row/column parity supplies linear equations over
GF(2). The diagnostic classifies each post-source state with >=2 M residuals as
inconsistent, underdetermined, or uniquely solvable and compares any unique
solution with the frozen target endpoints.

No recovery mechanism, coefficient, threshold, parity code, seed, horizon, or
scientific gate changes.
"""
from __future__ import annotations

import json

from benchmarks.diagnose_w84_transition_observability import CASES
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

SAMPLES = 64
MAX_TARGETS = 8
TRIALS_PER_TARGET = 6
TRACE_HORIZON = 12


def _bit(value: str) -> int:
    if value == "A":
        return 0
    if value == "C":
        return 1
    raise ValueError("binary bit requested for non-binary phase")


def _gf2_solve(matrix: list[list[int]], rhs: list[int], variables: int) -> dict:
    """Gauss-Jordan solve over GF(2), returning status and unique solution."""
    aug = [row[:] + [value & 1] for row, value in zip(matrix, rhs)]
    pivot_cols: list[int] = []
    pivot_row = 0

    for col in range(variables):
        candidate = next(
            (r for r in range(pivot_row, len(aug)) if aug[r][col] & 1),
            None,
        )
        if candidate is None:
            continue
        aug[pivot_row], aug[candidate] = aug[candidate], aug[pivot_row]
        for r in range(len(aug)):
            if r != pivot_row and aug[r][col] & 1:
                aug[r] = [a ^ b for a, b in zip(aug[r], aug[pivot_row])]
        pivot_cols.append(col)
        pivot_row += 1
        if pivot_row == len(aug):
            break

    for row in aug:
        if not any(row[:variables]) and row[variables]:
            return {
                "status": "no_solution",
                "rank": len(pivot_cols),
                "variables": variables,
                "solution": None,
            }

    rank = len(pivot_cols)
    if rank < variables:
        return {
            "status": "multiple_solutions",
            "rank": rank,
            "variables": variables,
            "solution": None,
        }

    solution = [0] * variables
    for r, col in enumerate(pivot_cols):
        solution[col] = aug[r][variables]
    return {
        "status": "unique_solution",
        "rank": rank,
        "variables": variables,
        "solution": solution,
    }


def _equations(model: CausalLocalityAuthorityGrid2D, unknowns: list[int]) -> tuple[list[list[int]], list[int]]:
    index_of = {cell: i for i, cell in enumerate(unknowns)}
    matrix: list[list[int]] = []
    rhs: list[int] = []
    width = model.config.width
    height = model.config.height

    for row in range(height):
        coeff = [0] * len(unknowns)
        known_xor = 0
        for col in range(width):
            index = row * width + col
            if index in index_of:
                coeff[index_of[index]] ^= 1
            else:
                known_xor ^= _bit(model.states[index])
        matrix.append(coeff)
        rhs.append(model.row_parity[row] ^ known_xor)

    for col in range(width):
        coeff = [0] * len(unknowns)
        known_xor = 0
        for row in range(height):
            index = row * width + col
            if index in index_of:
                coeff[index_of[index]] ^= 1
            else:
                known_xor ^= _bit(model.states[index])
        matrix.append(coeff)
        rhs.append(model.column_parity[col] ^ known_xor)

    return matrix, rhs


def _virtual_parity_ok(model: CausalLocalityAuthorityGrid2D, unknowns: list[int], bits: list[int]) -> bool:
    virtual = model.states.copy()
    for index, bit in zip(unknowns, bits):
        virtual[index] = "C" if bit else "A"
    rows, columns = model._parity("".join(virtual))
    return rows == model.row_parity and columns == model.column_parity


def _replay_case(case: dict) -> list[dict]:
    base = _manifest()
    width, height = case["width"], case["height"]
    cells = width * height
    config, hierarchy = _s2_components(base, width, height)
    targets = _fixed_binary_targets(
        _sha_binary_seeds(case["seed"], SAMPLES, cells), config, hierarchy, 6
    )[:MAX_TARGETS]
    target = targets[case["target_index"]]
    source = _noise_indices(
        case["seed"], case["target_index"], cells, TRIALS_PER_TARGET
    )[case["trial_index"]]
    if source != case["source"]:
        raise AssertionError(
            f"frozen source drift: expected {case['source']} got {source}"
        )

    model = CausalLocalityAuthorityGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=_m2_law(base),
        witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
    )
    _corrupt_all(model, source)
    rows: list[dict] = []

    for tick in range(1, TRACE_HORIZON + 1):
        model.step(0.0)
        source_repaired = model.states[source] == target[source]
        error_indices = [
            i for i, (actual, expected) in enumerate(zip(model.states, target))
            if actual != expected
        ]
        m_indices = [i for i in error_indices if model.states[i] == "M"]
        wrong_binary = [
            i for i in error_indices if model.states[i] in ("A", "C")
        ]
        if not source_repaired or len(m_indices) < 2:
            continue

        matrix, rhs = _equations(model, m_indices)
        solved = _gf2_solve(matrix, rhs, len(m_indices))
        target_bits = [_bit(target[index]) for index in m_indices]
        solution = solved["solution"]
        unique_correct = (
            solved["status"] == "unique_solution" and solution == target_bits
        )
        virtual_ok = (
            _virtual_parity_ok(model, m_indices, solution)
            if solution is not None
            else False
        )
        rows.append(
            {
                "class": case["class"],
                "width": width,
                "height": height,
                "seed": case["seed"],
                "target_index": case["target_index"],
                "trial_index": case["trial_index"],
                "source": source,
                "tick": tick,
                "m_indices": m_indices,
                "m_count": len(m_indices),
                "wrong_binary_indices": wrong_binary,
                "wrong_binary_count": len(wrong_binary),
                "solver_status": solved["status"],
                "rank": solved["rank"],
                "variables": solved["variables"],
                "solution_bits": solution,
                "target_bits": target_bits,
                "unique_solution_matches_target": unique_correct,
                "virtual_full_parity_ok": virtual_ok,
            }
        )
    return rows


def run_diagnostic() -> dict:
    rows = [row for case in CASES for row in _replay_case(case)]
    persistent = [row for row in rows if row["class"] == "persistent"]
    late = [row for row in rows if row["class"] == "late"]

    def count(group: list[dict], status: str) -> int:
        return sum(row["solver_status"] == status for row in group)

    unique_wrong = [
        row
        for row in rows
        if row["solver_status"] == "unique_solution"
        and not row["unique_solution_matches_target"]
    ]
    uniquely_correct = [
        row for row in rows if row["unique_solution_matches_target"]
    ]
    unique_correct_with_wrong_binary = [
        row for row in uniquely_correct if row["wrong_binary_count"] > 0
    ]

    summary = {
        "multi_m_states": len(rows),
        "persistent_multi_m_states": len(persistent),
        "late_multi_m_states": len(late),
        "unique_solution_states": count(rows, "unique_solution"),
        "multiple_solution_states": count(rows, "multiple_solutions"),
        "no_solution_states": count(rows, "no_solution"),
        "unique_solution_matches_target": len(uniquely_correct),
        "unique_solution_wrong_target": len(unique_wrong),
        "unique_correct_with_wrong_binary_present": len(
            unique_correct_with_wrong_binary
        ),
        "persistent_unique_solution_states": count(
            persistent, "unique_solution"
        ),
        "persistent_multiple_solution_states": count(
            persistent, "multiple_solutions"
        ),
        "persistent_no_solution_states": count(persistent, "no_solution"),
        "late_unique_solution_states": count(late, "unique_solution"),
        "late_multiple_solution_states": count(late, "multiple_solutions"),
        "late_no_solution_states": count(late, "no_solution"),
        "all_unique_solutions_pass_virtual_parity": all(
            row["virtual_full_parity_ok"]
            for row in rows
            if row["solver_status"] == "unique_solution"
        ),
    }

    return {
        "schema": "cosmic-organics/w84-multierasure-solvability-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_pr": 47,
        "summary": summary,
        "unique_wrong_states": unique_wrong,
        "states": rows,
        "decision_contract": (
            "a multi-erasure observability mechanism is admissible only for states "
            "where the existing committed parity equations have a unique solution, "
            "the inferred endpoints agree with frozen truth in diagnostic evaluation, "
            "and full virtual parity validation succeeds; ambiguous or inconsistent "
            "states must fail closed"
        ),
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
