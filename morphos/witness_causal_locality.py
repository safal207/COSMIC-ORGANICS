"""MORPHOS-W8.4 causal-locality handoff.

W8.3 fresh confirmation exposed a different two-error residual after the
original protected source was independently repaired: two binary collateral
errors remained on opposite immediate neighbours of the verified source in the
same row. Their row parity cancelled, leaving only two bad columns, so the W8.3
2x2 history-pair decoder correctly failed closed.

A follow-up diagnostic replayed 864 already-observed trials. All three observed
post-source two-error residuals were direct von-Neumann neighbours of the source,
and the narrow cancelled-axis predicate fired exactly once, correctly, with zero
false positives. That evidence admits only this bounded development experiment;
it does not establish a generic locality law.

W8.4 is therefore a fallback *after* ordinary W5/W6 and W8.3 decoding. It may
infer a pair only inside an existing one-source repair transaction when the
source is verified at its witnessed endpoint and parity has exactly one cancelled
axis: 0 bad rows x 2 bad columns, or symmetrically 2 bad rows x 0 bad columns.
The verified source supplies the missing coordinate. Both inferred cells must be
immediate opposite neighbours of the source, binary, unprotected, and their
virtual flip must reproduce the complete committed parity witness. Only then are
they added to W7's existing concurrent repair set.

No witness amplitude, threshold, coupling, commit delay, horizon, or parity code
is changed. This is a classical deterministic software/control experiment.
"""
from __future__ import annotations

from morphos.witness_history_pair import HistoryAwarePairAuthorityGrid2D


class CausalLocalityAuthorityGrid2D(HistoryAwarePairAuthorityGrid2D):
    """Use verified source locality to reconstruct one cancelled parity axis."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.locality_pair_decode_events = 0
        self.locality_pair_added_targets = 0
        self.locality_pair_reject_events = 0
        self.locality_pair_virtual_parity_reject_events = 0
        self.locality_pair_history_reject_events = 0
        self.last_locality_pair: tuple[int, int] | None = None

    def _cancelled_axis_pair(self) -> tuple[int, int] | None:
        if (
            not self.selective_fence_active
            or self.witness_law.witness_drive <= 0
            or self.latched_index is None
            or self.latched_target not in ("A", "C")
            or len(self.protected_targets) != 1
        ):
            return None

        verified = self._verified_protected_indices()
        if verified != {self.latched_index}:
            self.locality_pair_history_reject_events += 1
            return None

        bad_rows, bad_columns = self.syndrome()
        width = self.config.width
        height = self.config.height
        source_row, source_column = divmod(self.latched_index, width)

        pair: tuple[int, int] | None = None
        if len(bad_rows) == 0 and len(bad_columns) == 2:
            # Row parity cancelled. The verified source supplies the row, while
            # the two surviving columns must be its immediate left/right cells.
            expected_columns = {source_column - 1, source_column + 1}
            if (
                source_column <= 0
                or source_column >= width - 1
                or set(bad_columns) != expected_columns
            ):
                return None
            pair = tuple(
                sorted(source_row * width + column for column in bad_columns)
            )
        elif len(bad_rows) == 2 and len(bad_columns) == 0:
            # Column parity cancelled. The verified source supplies the column,
            # while the two surviving rows must be its immediate up/down cells.
            expected_rows = {source_row - 1, source_row + 1}
            if (
                source_row <= 0
                or source_row >= height - 1
                or set(bad_rows) != expected_rows
            ):
                return None
            pair = tuple(
                sorted(row * width + source_column for row in bad_rows)
            )
        else:
            return None

        if self.latched_index in pair:
            self.locality_pair_history_reject_events += 1
            return None
        if any(index in self.protected_targets for index in pair):
            self.locality_pair_history_reject_events += 1
            return None
        if any(self.states[index] not in ("A", "C") for index in pair):
            self.locality_pair_reject_events += 1
            return None
        return pair

    def _locality_pair_decode(self) -> bool:
        pair = self._cancelled_axis_pair()
        if pair is None:
            return False
        if not self._virtual_pair_restores_committed_parity(pair):
            self.locality_pair_virtual_parity_reject_events += 1
            return False

        for index in pair:
            self.protected_targets[index] = self._opposite(self.states[index])
        self.locality_pair_decode_events += 1
        self.locality_pair_added_targets += 2
        self.last_locality_pair = pair
        self.max_repair_set_size = max(
            self.max_repair_set_size, len(self.protected_targets)
        )
        return True

    def _handoff_if_migrated(self) -> None:
        previous_handoffs = self.handoff_events
        previous_size = len(self.protected_targets)
        previous_history_pair_events = self.history_pair_decode_events
        super()._handoff_if_migrated()

        # W5/W6 and W8.3 retain strict priority. W8.4 may act only when none of
        # those mechanisms changed repair ownership in this step.
        if (
            self.handoff_events != previous_handoffs
            or len(self.protected_targets) != previous_size
            or self.history_pair_decode_events != previous_history_pair_events
        ):
            return
        self._locality_pair_decode()
