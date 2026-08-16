"""MORPHOS-W5 moving witness ownership for migrated repair syndromes.

W4 can repair the originally witnessed cell while a one-cell residual error
moves into a direct neighbour. Because W4 keeps the repair latch attached to
the original cell until the whole transaction commits, a newly unique parity
syndrome can remain visible but unowned.

W5 changes only repair ownership. The independently witnessed drive, mirror
couplings, thresholds, horizons, and commit delays remain unchanged. Once the
currently owned cell reaches its witnessed binary endpoint, a newly unique
syndrome may hand repair ownership to another binary cell. Previously repaired
cells remain protected from contradictory mirror authority until all touched
cells and their mirrors have recommitted and the witness is clean.

This is a classical algorithmic recovery experiment, not quantum error
correction and not a physical material implementation.
"""
from __future__ import annotations

from typing import Sequence

from morphos.witness_selective import SelectiveAuthorityGrid2D, _VALUE


class HandoffAuthorityGrid2D(SelectiveAuthorityGrid2D):
    """Transfer repair ownership when an independently localized error moves."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.protected_targets: dict[int, str] = {}
        self.handoff_events = 0
        self.handoff_history: list[tuple[int, int]] = []

    def _open_fence_if_localized(self) -> None:
        if not self.selective_fence_active:
            super()._open_fence_if_localized()
            if (
                self.selective_fence_active
                and self.latched_index is not None
                and self.latched_target is not None
            ):
                self.protected_targets.setdefault(
                    self.latched_index, self.latched_target
                )
            return

        self._handoff_if_migrated()

    def _handoff_if_migrated(self) -> None:
        if (
            not self.selective_fence_active
            or self.latched_index is None
            or self.latched_target is None
            or self.witness_law.witness_drive <= 0
        ):
            return

        # Do not chase a transient syndrome while the current owner is still
        # traversing A/C -> M -> C/A. Handoff becomes legal only after the
        # currently owned primary cell has reached its witnessed endpoint.
        if self.states[self.latched_index] != self.latched_target:
            return

        localized = self.localized_error_index()
        if localized is None or localized == self.latched_index:
            return
        current = self.states[localized]
        if current not in ("A", "C"):
            return

        previous = self.latched_index
        target = self._opposite_binary(current)
        self.protected_targets.setdefault(previous, self.latched_target)
        self.protected_targets[localized] = target
        self.latched_index = localized
        self.latched_target = target
        self.latch_events += 1
        self.handoff_events += 1
        self.handoff_history.append((previous, localized))

    def _mirror_drive(
        self,
        *,
        index: int,
        phase: str,
        mirror_phase: str,
        coupling: float,
    ) -> float:
        delta = _VALUE[mirror_phase] - _VALUE[phase]
        if self.selective_fence_active and index in self.protected_targets:
            target = self.protected_targets[index]
            if mirror_phase != target:
                self.suppressed_mirror_contributions += 1
                return 0.0
            self.preserved_mirror_contributions += 1
        return coupling * delta

    def _all_repair_targets_committed(self) -> bool:
        if not self.protected_targets:
            return False
        for index, target in self.protected_targets.items():
            if self.states[index] != target:
                return False
            if self.local_mirror_states[index] != target:
                return False
            if self.domain_mirror_states[index] != target:
                return False
            if self.system_mirror_states[index] != target:
                return False
        return True

    def _release_fence_if_committed(self) -> None:
        if not self.selective_fence_active:
            return
        witness_agrees = self.syndrome() == ((), ())
        if witness_agrees and self._all_repair_targets_committed():
            self.selective_fence_active = False
            self.latched_index = None
            self.latched_target = None
            self.protected_targets.clear()
            self.latch_clear_events += 1
            self.fence_release_events += 1

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        stimuli = self._normalize_stimulus(stimulus, len(self.states))
        non_quiescent = not self._quiescent(stimuli)
        if non_quiescent:
            # Explicit external intent keeps W4's adaptation semantics and
            # cancels any quiescent repair-ownership chain.
            self.protected_targets.clear()
        super().step(stimuli)
