"""MORPHOS-W3 witness-validated recovery fence.

W3 treats recovery as a two-phase transaction. A parity witness can open a
repair fence under quiescent input, temporarily removing authority from stale
copy-like mirrors while the primary is corrected. Mirror authority is restored
only after primary, witness, and all mirror planes agree again.

Non-zero external stimulus is treated as an active transition request rather
than a quiescent fault-recovery episode; W3 falls back to W1-style witness
behavior so sustained intended change can still be learned.

This is a classical algorithmic recovery experiment, not quantum error
correction and not a physical material implementation.
"""
from __future__ import annotations

from typing import Sequence

from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw
from morphos.witness import IndependentWitnessGrid2D
from morphos.witness_persistent import PersistentWitnessGrid2D


class RecoveryFenceGrid2D(PersistentWitnessGrid2D):
    """Persistent witness intent plus temporary quarantine of stale mirrors."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.recovery_fence_active = False
        self.fence_open_events = 0
        self.fence_release_events = 0
        self.fence_abort_for_stimulus_events = 0
        self.fenced_ticks = 0

    @staticmethod
    def _normalize_stimulus(
        stimulus: float | Sequence[float],
        count: int,
    ) -> list[float]:
        if isinstance(stimulus, (int, float)):
            return [float(stimulus)] * count
        values = [float(value) for value in stimulus]
        if len(values) != count:
            raise ValueError("stimulus sequence length must equal cell count")
        return values

    @staticmethod
    def _quiescent(stimuli: Sequence[float]) -> bool:
        return all(abs(value) <= 1e-12 for value in stimuli)

    def _mirrors_match_primary(self) -> bool:
        primary = self.state_string()
        return (
            self.local_mirror_string() == primary
            and self.domain_mirror_string() == primary
            and self.system_mirror_string() == primary
        )

    def _open_fence_if_localized(self) -> None:
        if self.recovery_fence_active or self.witness_law.witness_drive <= 0:
            return
        self._maybe_latch_from_syndrome()
        if self.latched_index is not None:
            self.recovery_fence_active = True
            self.fence_open_events += 1

    def _release_fence_if_committed(self) -> None:
        if not self.recovery_fence_active:
            return
        if self.latched_index is None or self.latched_target is None:
            return
        target_reached = self.states[self.latched_index] == self.latched_target
        witness_agrees = self.syndrome() == ((), ())
        mirrors_agree = self._mirrors_match_primary()
        if target_reached and witness_agrees and mirrors_agree:
            self.recovery_fence_active = False
            self.latched_index = None
            self.latched_target = None
            self.latch_clear_events += 1
            self.fence_release_events += 1

    def _zero_coupling_law(self) -> MultiReflectiveLaw:
        base = self.reflective_law
        return MultiReflectiveLaw(
            local_coupling=0.0,
            domain_coupling=0.0,
            system_coupling=0.0,
            local_commit_delay=base.local_commit_delay,
            domain_commit_delay=base.domain_commit_delay,
            system_commit_delay=base.system_commit_delay,
        )

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        stimuli = self._normalize_stimulus(stimulus, len(self.states))

        # An explicit non-zero stimulus is an active transition request rather
        # than a quiescent recovery episode. Abort an outstanding fence and use
        # W1-style witness dynamics so sustained intended transitions remain
        # learnable instead of being permanently pinned to the old state.
        if not self._quiescent(stimuli):
            if self.recovery_fence_active:
                self.recovery_fence_active = False
                self.latched_index = None
                self.latched_target = None
                self.fence_abort_for_stimulus_events += 1
            IndependentWitnessGrid2D.step(self, stimuli)
            return

        previous_primary = self.state_string()
        syndrome = self.syndrome()
        self.last_syndrome = syndrome
        self.last_localized_index = self.localized_error_index()
        if syndrome != ((), ()):
            self.syndrome_events += 1

        self._open_fence_if_localized()
        if self.recovery_fence_active:
            self.localized_events += 1
            self._apply_latched_drive(stimuli)
            self.fenced_ticks += 1

        base_law = self.reflective_law
        if self.recovery_fence_active:
            self.reflective_law = self._zero_coupling_law()
        try:
            # Commit counters remain active while mirror influence is fenced;
            # stale mirrors can therefore be rewritten from a stable repaired
            # primary without being allowed to pull that primary backward.
            MultiReflectiveGrid2D.step(self, stimuli)
        finally:
            self.reflective_law = base_law

        self._release_fence_if_committed()

        # The parity witness is authoritative during an open repair transaction
        # and must not be rewritten from an uncommitted intermediate state.
        if not self.recovery_fence_active:
            self._update_witness_commit(previous_primary, self.state_string())
