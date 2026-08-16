"""MORPHOS-W2 transition-aware persistent witness intent.

W2 preserves the intended binary endpoint across MORPHOS's mandatory mixed
phase. A row/column parity syndrome first localizes a single-bit error while
the state is binary. The decoder then latches both the cell index and the
opposite binary phase and keeps applying the same bounded transition drive
until that cell reaches the latched endpoint.

This is a classical algorithmic decoder experiment, not quantum error
correction and not a physical material implementation.
"""
from __future__ import annotations

from typing import Sequence

from morphos.multimirror import MultiReflectiveGrid2D
from morphos.witness import IndependentWitnessGrid2D, WitnessLaw


class PersistentWitnessGrid2D(IndependentWitnessGrid2D):
    """Independent parity witness whose corrective intent survives `M`."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.latched_index: int | None = None
        self.latched_target: str | None = None
        self.latch_events = 0
        self.latch_clear_events = 0
        self.latched_drive_steps = 0

    @staticmethod
    def _opposite_binary(value: str) -> str:
        if value == "A":
            return "C"
        if value == "C":
            return "A"
        raise ValueError("latched target requires binary A/C source")

    def _maybe_latch_from_syndrome(self) -> None:
        if self.latched_index is not None:
            return
        localized = self.localized_error_index()
        if localized is None:
            return
        current = self.states[localized]
        if current not in ("A", "C"):
            return
        self.latched_index = localized
        self.latched_target = self._opposite_binary(current)
        self.latch_events += 1

    def _apply_latched_drive(self, stimuli: list[float]) -> None:
        if self.latched_index is None or self.latched_target is None:
            return
        current = self.states[self.latched_index]
        if current == self.latched_target:
            return
        direction = 1.0 if self.latched_target == "C" else -1.0
        stimuli[self.latched_index] += direction * self.witness_law.witness_drive
        self.latched_drive_steps += 1

    def _update_witness_commit(
        self,
        previous_primary: str,
        current_primary: str,
    ) -> None:
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

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        if isinstance(stimulus, (int, float)):
            stimuli = [float(stimulus)] * len(self.states)
        else:
            stimuli = [float(value) for value in stimulus]
            if len(stimuli) != len(self.states):
                raise ValueError("stimulus sequence length must equal cell count")

        previous_primary = self.state_string()
        syndrome = self.syndrome()
        self.last_syndrome = syndrome
        self.last_localized_index = self.localized_error_index()
        if syndrome != ((), ()):
            self.syndrome_events += 1

        self._maybe_latch_from_syndrome()
        if self.latched_index is not None:
            self.localized_events += 1
        self._apply_latched_drive(stimuli)

        # Bypass W1.step so binary-only syndrome logic does not replace the
        # latched intent during the intermediate M phase.
        MultiReflectiveGrid2D.step(self, stimuli)

        current_primary = self.state_string()
        if (
            self.latched_index is not None
            and self.latched_target is not None
            and self.states[self.latched_index] == self.latched_target
        ):
            # The intended endpoint has been reached. Clear only after the
            # primary plane again agrees with the committed parity witness.
            if self.syndrome() == ((), ()):
                self.latched_index = None
                self.latched_target = None
                self.latch_clear_events += 1

        self._update_witness_commit(previous_primary, current_primary)
