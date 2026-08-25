"""MORPHOS-W7 concurrent repair-set stabilization.

W6 can decode a migrated `M` erasure and hand repair ownership to it, but the
post-endpoint diagnostic found deterministic two-cell ping-pong in all nine
frozen mixed-erasure cases. The transaction already remembers both touched
endpoints in ``protected_targets`` while the active corrective drive remains
exclusive to one ``latched_index``. Moving that single pointer therefore
removes active support from the previous, not-yet-recommitted repair.

W7 changes only the control-state shape: while a quiescent repair transaction
is open, every touched target in ``protected_targets`` receives the same
bounded witness drive toward its independently established endpoint until the
whole repair set and its mirrors recommit. No drive amplitude, threshold,
coupling, commit delay, horizon, decoder, or witness code is changed.

This is a classical algorithmic recovery experiment, not quantum error
correction and not a physical material implementation.
"""
from __future__ import annotations

from morphos.witness_erasure import ErasureAwareAuthorityGrid2D


class RepairSetAuthorityGrid2D(ErasureAwareAuthorityGrid2D):
    """Keep active corrective intent on all uncommitted repair obligations."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.repair_set_drive_steps = 0
        self.repair_set_target_drive_steps = 0
        self.max_repair_set_size = 0

    def _apply_latched_drive(self, stimuli: list[float]) -> None:
        # Before a W5/W6 repair fence exists, preserve the historical W2
        # single-latch behavior exactly.
        if not self.selective_fence_active or not self.protected_targets:
            super()._apply_latched_drive(stimuli)
            return

        self.max_repair_set_size = max(
            self.max_repair_set_size, len(self.protected_targets)
        )
        self.repair_set_drive_steps += 1

        # A repair obligation remains active until transaction-level recommit,
        # even if its primary cell is currently at the endpoint. This bounded
        # hold is what prevents a freshly repaired owner from rebounding while
        # responsibility is added for another witnessed cell.
        for index, target in sorted(self.protected_targets.items()):
            direction = 1.0 if target == "C" else -1.0
            stimuli[index] += direction * self.witness_law.witness_drive
            self.repair_set_target_drive_steps += 1
            self.latched_drive_steps += 1
