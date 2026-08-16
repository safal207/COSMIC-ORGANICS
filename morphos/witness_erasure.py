"""MORPHOS-W6 erasure-aware transition witness.

W5 can transfer repair ownership only when the binary row/column parity witness
uniquely localizes a migrated A/C error. Diagnostics showed a different dominant
boundary: after the original source repairs, a single neighbouring cell can
remain in MORPHOS's known transition phase `M`. W1's binary syndrome then fails
closed for the whole grid, so W5 cannot hand ownership to that cell.

W6 does not change the historical binary syndrome. It adds a narrower decoder
for exactly one known erasure. The committed row parity and committed column
parity independently infer the missing bit. The decoder accepts the erasure
only when both projections agree *and* substituting that inferred endpoint
makes the complete virtual binary state match every committed row/column parity.
Otherwise it fails closed.

No amplitude, threshold, coupling, commit delay, or horizon is changed.
This is a classical algorithmic recovery experiment, not quantum error
correction and not a physical material implementation.
"""
from __future__ import annotations

from morphos.witness_handoff import HandoffAuthorityGrid2D


class ErasureAwareAuthorityGrid2D(HandoffAuthorityGrid2D):
    """W5 plus single-`M` erasure localization for repair handoff."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.erasure_localization_events = 0
        self.erasure_handoff_events = 0
        self.erasure_reject_events = 0
        self.last_erasure_localization: tuple[int, str] | None = None

    def erasure_aware_localization(self) -> tuple[int, str] | None:
        """Infer one `M` endpoint from committed row and column parity.

        The method is deliberately stricter than merely filling the unknown bit:
        after row/column inference agree, the complete virtual binary state must
        exactly reproduce all committed parity bits. This rejects a known `M`
        accompanied by any parity-visible binary errors.
        """

        mixed = [index for index, value in enumerate(self.states) if value == "M"]
        if len(mixed) != 1:
            self.last_erasure_localization = None
            self.erasure_reject_events += 1
            return None

        index = mixed[0]
        row, column = divmod(index, self.config.width)

        row_bit = self.row_parity[row]
        row_start = row * self.config.width
        for other in range(row_start, row_start + self.config.width):
            if other == index:
                continue
            value = self.states[other]
            if value not in ("A", "C"):
                self.last_erasure_localization = None
                self.erasure_reject_events += 1
                return None
            row_bit ^= self._bit(value)

        column_bit = self.column_parity[column]
        for other_row in range(self.config.height):
            other = other_row * self.config.width + column
            if other == index:
                continue
            value = self.states[other]
            if value not in ("A", "C"):
                self.last_erasure_localization = None
                self.erasure_reject_events += 1
                return None
            column_bit ^= self._bit(value)

        if row_bit != column_bit:
            self.last_erasure_localization = None
            self.erasure_reject_events += 1
            return None

        target = "C" if row_bit else "A"
        virtual = self.states.copy()
        virtual[index] = target
        rows, columns = self._parity("".join(virtual))
        if rows != self.row_parity or columns != self.column_parity:
            self.last_erasure_localization = None
            self.erasure_reject_events += 1
            return None

        result = (index, target)
        self.last_erasure_localization = result
        self.erasure_localization_events += 1
        return result

    def _handoff_if_migrated(self) -> None:
        previous_handoffs = self.handoff_events
        super()._handoff_if_migrated()
        if self.handoff_events != previous_handoffs:
            return

        if (
            not self.selective_fence_active
            or self.latched_index is None
            or self.latched_target is None
            or self.witness_law.witness_drive <= 0
        ):
            return

        # Preserve W5's ownership rule: do not transfer responsibility until
        # the current owner itself has reached the witnessed endpoint.
        if self.states[self.latched_index] != self.latched_target:
            return

        decoded = self.erasure_aware_localization()
        if decoded is None:
            return
        localized, target = decoded
        if localized == self.latched_index:
            return

        previous = self.latched_index
        self.protected_targets.setdefault(previous, self.latched_target)
        self.protected_targets[localized] = target
        self.latched_index = localized
        self.latched_target = target
        self.latch_events += 1
        self.handoff_events += 1
        self.erasure_handoff_events += 1
        self.handoff_history.append((previous, localized))
