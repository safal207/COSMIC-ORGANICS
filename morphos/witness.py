"""MORPHOS-W1 independently encoded parity witness.

W1 does not add another copy-like mirror. It stores row/column parity of the
last committed binary primary state. For a single-bit primary error, the
syndrome can localize the disagreeing cell even when primary/local/domain/
system planes all share the same corrupted value.

This is a classical algorithmic error-correction experiment, not quantum error
correction and not a physical material implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalLaw
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw


@dataclass(frozen=True)
class WitnessLaw:
    witness_drive: float = 0.75
    commit_delay: int = 8

    def __post_init__(self) -> None:
        if self.witness_drive < 0:
            raise ValueError("witness_drive must be non-negative")
        if self.commit_delay <= 0:
            raise ValueError("commit_delay must be positive")


class IndependentWitnessGrid2D(MultiReflectiveGrid2D):
    """M2 plus a non-copy row/column parity witness for binary states."""

    def __init__(
        self,
        initial: str,
        *,
        config: Grid2DConfig,
        law: HierarchicalLaw,
        reflective_law: MultiReflectiveLaw | None = None,
        witness_law: WitnessLaw | None = None,
    ) -> None:
        if any(value not in ("A", "C") for value in initial):
            raise ValueError("W1 initialization requires binary A/C state")
        super().__init__(
            initial,
            config=config,
            law=law,
            reflective_law=reflective_law,
        )
        self.witness_law = witness_law or WitnessLaw()
        self.row_parity, self.column_parity = self._parity(initial)
        self.witness_stable_count = 0
        self.witness_commit_events = 0
        self.syndrome_events = 0
        self.localized_events = 0
        self.last_syndrome: tuple[tuple[int, ...], tuple[int, ...]] = ((), ())
        self.last_localized_index: int | None = None

    @staticmethod
    def _bit(value: str) -> int:
        if value == "A":
            return 0
        if value == "C":
            return 1
        raise ValueError("parity is defined only for binary A/C states")

    def _parity(self, state: str) -> tuple[list[int], list[int]]:
        rows = [0] * self.config.height
        columns = [0] * self.config.width
        for index, value in enumerate(state):
            bit = self._bit(value)
            row, column = divmod(index, self.config.width)
            rows[row] ^= bit
            columns[column] ^= bit
        return rows, columns

    def syndrome(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        if any(value not in ("A", "C") for value in self.states):
            return (), ()
        rows, columns = self._parity(self.state_string())
        bad_rows = tuple(
            index
            for index, (actual, expected) in enumerate(zip(rows, self.row_parity))
            if actual != expected
        )
        bad_columns = tuple(
            index
            for index, (actual, expected) in enumerate(zip(columns, self.column_parity))
            if actual != expected
        )
        return bad_rows, bad_columns

    def localized_error_index(self) -> int | None:
        bad_rows, bad_columns = self.syndrome()
        if len(bad_rows) == 1 and len(bad_columns) == 1:
            return bad_rows[0] * self.config.width + bad_columns[0]
        return None

    def perturb_witness_for_cell(self, index: int) -> None:
        if not 0 <= index < len(self.states):
            raise IndexError("perturbation index out of range")
        row, column = divmod(index, self.config.width)
        self.row_parity[row] ^= 1
        self.column_parity[column] ^= 1

    def witness_signature(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        return tuple(self.row_parity), tuple(self.column_parity)

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        if isinstance(stimulus, (int, float)):
            stimuli = [float(stimulus)] * len(self.states)
        else:
            stimuli = [float(value) for value in stimulus]
            if len(stimuli) != len(self.states):
                raise ValueError("stimulus sequence length must equal cell count")

        previous_primary = self.state_string()
        syndrome = self.syndrome()
        localized = self.localized_error_index()
        self.last_syndrome = syndrome
        self.last_localized_index = localized
        if syndrome != ((), ()):
            self.syndrome_events += 1
        if localized is not None:
            self.localized_events += 1
            current = self.states[localized]
            if current in ("A", "C"):
                direction = 1.0 if current == "A" else -1.0
                stimuli[localized] += direction * self.witness_law.witness_drive

        super().step(stimuli)

        current_primary = self.state_string()
        binary = all(value in ("A", "C") for value in self.states)
        mirrors_agree = (
            self.local_mirror_string() == current_primary
            and self.domain_mirror_string() == current_primary
            and self.system_mirror_string() == current_primary
        )
        unchanged = current_primary == previous_primary
        if binary and mirrors_agree and unchanged:
            self.witness_stable_count += 1
        else:
            self.witness_stable_count = 0

        if self.witness_stable_count >= self.witness_law.commit_delay:
            rows, columns = self._parity(current_primary)
            if rows != self.row_parity or columns != self.column_parity:
                self.row_parity = rows
                self.column_parity = columns
                self.witness_commit_events += 1
            self.witness_stable_count = 0
