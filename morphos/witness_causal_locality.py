"""MORPHOS-W8.4 causal-locality handoff for cancelled-axis pair residuals.

W8.3 resolves a 2x2 parity ambiguity when repair history excludes the pairing
that contains an already verified source. Fresh confirmation exposed a different
repair-induced pair: after source repair, two immediate neighbours on the same
row remained wrong. Their even row parity cancels, leaving only two bad columns.

Observed-evidence diagnostics across 864 already-seen W8.2/W8.3 trials found
three post-source binary pair states; all three consisted only of immediate
von-Neumann neighbours of the verified source. A narrow cancelled-axis predicate
fired once, on the known same-row residual, with zero false positives.

W8.4 is therefore a deliberately narrow fallback, not a generic two-error
decoder. After W5/W6 and W8.3 have failed to expand ownership, it may use the
verified source coordinate to restore a parity-cancelled axis only when the two
inferred cells are immediate source neighbours, binary, unprotected, and their
virtual flip restores the complete committed parity witness.

No witness amplitude, threshold, coupling, parity code, commit delay, or horizon
is changed. Classical deterministic software/control experiment only.
"""
from __future__ import annotations

from morphos.witness_history_pair import HistoryAwarePairAuthorityGrid2D


class CausalLocalityAuthorityGrid2D(HistoryAwarePairAuthorityGrid2D):
    """Use verified source locality only for parity-axis cancellation residuals."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.locality_pair_decode_events = 0
        self.locality_pair_added_targets = 0
        self.locality_pair_reject_events = 0
        self.locality_pair_virtual_parity_reject_events = 0
        self.last_locality_pair: tuple[int, int] | None = None
        self.last_locality_kind: str | None = None

    def _direct_neighbor(self, source: int, other: int) -> bool:
        sr, sc = divmod(source, self.config.width)
        rr, rc = divmod(other, self.config.width)
        return abs(rr - sr) + abs(rc - sc) == 1

    def _cancelled_axis_candidate(
        self, source: int
    ) -> tuple[tuple[int, int], str] | None:
        bad_rows, bad_columns = self.syndrome()
        sr, sc = divmod(source, self.config.width)

        if len(bad_rows) == 0 and len(bad_columns) == 2:
            pair = tuple(
                sorted(sr * self.config.width + column for column in bad_columns)
            )
            kind = "same_row_cancelled"
        elif len(bad_rows) == 2 and len(bad_columns) == 0:
            pair = tuple(
                sorted(row * self.config.width + sc for row in bad_rows)
            )
            kind = "same_column_cancelled"
        else:
            return None

        if source in pair:
            return None
        if any(index in self.protected_targets for index in pair):
            return None
        if any(self.states[index] not in ("A", "C") for index in pair):
            return None
        if not all(self._direct_neighbor(source, index) for index in pair):
            return None
        return pair, kind

    def _locality_pair_decode(self) -> bool:
        if (
            not self.selective_fence_active
            or self.witness_law.witness_drive <= 0
            or self.latched_index is None
            or self.latched_target not in ("A", "C")
            or len(self.protected_targets) != 1
        ):
            return False

        source = self.latched_index
        verified = self._verified_protected_indices()
        if verified != {source}:
            return False

        decoded = self._cancelled_axis_candidate(source)
        if decoded is None:
            return False
        pair, kind = decoded

        if not self._virtual_pair_restores_committed_parity(pair):
            self.locality_pair_virtual_parity_reject_events += 1
            return False

        for index in pair:
            self.protected_targets[index] = self._opposite(self.states[index])
        self.locality_pair_decode_events += 1
        self.locality_pair_added_targets += 2
        self.last_locality_pair = pair
        self.last_locality_kind = kind
        self.max_repair_set_size = max(
            self.max_repair_set_size, len(self.protected_targets)
        )
        return True

    def _handoff_if_migrated(self) -> None:
        previous_handoffs = self.handoff_events
        previous_history = self.history_pair_decode_events
        previous_size = len(self.protected_targets)
        super()._handoff_if_migrated()

        # Existing W5/W6/W8.3 semantics always have priority. Locality is only
        # a final fallback when no earlier decoder expanded/changed ownership.
        if (
            self.handoff_events != previous_handoffs
            or self.history_pair_decode_events != previous_history
            or len(self.protected_targets) != previous_size
        ):
            return
        self._locality_pair_decode()
