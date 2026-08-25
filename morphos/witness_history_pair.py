"""MORPHOS-W8.3 repair-history-aware pair handoff.

W8.2 fresh confirmation exposed a narrow two-error ambiguity: after the original
protected source is independently restored, two orthogonal collateral binary
errors can remain. Row/column parity then yields two perfect row/column
matchings. Diagnostic evidence showed that, in both frozen residuals, one
matching contains the already protected and now-correct source while the other
matching is the actual residual pair.

W8.3 does not claim generic two-error correction. It may decode a pair only
inside an existing quiescent repair transaction, after ordinary W5/W6 handoff
has failed, when exactly one protected source is verified at its witnessed
endpoint. The verified source removes candidate matchings that would contradict
repair history. The sole surviving pair is accepted only if virtually flipping
exactly those two binary cells reproduces the complete committed row/column
parity witness. Both obligations are then added to W7's existing repair set.

No witness amplitude, threshold, coupling, commit delay, horizon, or parity code
is changed. This is a classical deterministic software/control experiment.
"""
from __future__ import annotations

from morphos.witness_executable_margin import ExecutableMarginClosureGrid2D


class HistoryAwarePairAuthorityGrid2D(ExecutableMarginClosureGrid2D):
    """Use verified repair history to disambiguate one 2x2 parity syndrome."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.history_pair_decode_events = 0
        self.history_pair_added_targets = 0
        self.history_pair_reject_events = 0
        self.history_pair_virtual_parity_reject_events = 0
        self.history_pair_history_reject_events = 0
        self.last_history_pair: tuple[int, int] | None = None

    def _verified_protected_indices(self) -> set[int]:
        return {
            index
            for index, target in self.protected_targets.items()
            if target in ("A", "C") and self.states[index] == target
        }

    def _two_error_matchings(self) -> list[tuple[int, int]]:
        bad_rows, bad_columns = self.syndrome()
        if len(bad_rows) != 2 or len(bad_columns) != 2:
            return []
        r0, r1 = bad_rows
        c0, c1 = bad_columns
        width = self.config.width
        return [
            tuple(sorted((r0 * width + c0, r1 * width + c1))),
            tuple(sorted((r0 * width + c1, r1 * width + c0))),
        ]

    @staticmethod
    def _opposite(value: str) -> str:
        if value == "A":
            return "C"
        if value == "C":
            return "A"
        raise ValueError("history pair candidates must be binary")

    def _virtual_pair_restores_committed_parity(
        self, pair: tuple[int, int]
    ) -> bool:
        if any(self.states[index] not in ("A", "C") for index in pair):
            return False
        virtual = self.states.copy()
        for index in pair:
            virtual[index] = self._opposite(virtual[index])
        rows, columns = self._parity("".join(virtual))
        return rows == self.row_parity and columns == self.column_parity

    def _history_pair_decode(self) -> bool:
        if (
            not self.selective_fence_active
            or self.witness_law.witness_drive <= 0
            or self.latched_index is None
            or self.latched_target not in ("A", "C")
            or len(self.protected_targets) != 1
        ):
            return False

        verified = self._verified_protected_indices()
        if verified != {self.latched_index}:
            self.history_pair_history_reject_events += 1
            return False

        matchings = self._two_error_matchings()
        if len(matchings) != 2:
            return False

        compatible = [
            pair for pair in matchings if not any(index in verified for index in pair)
        ]
        if len(compatible) != 1:
            self.history_pair_history_reject_events += 1
            return False

        pair = compatible[0]
        if any(index in self.protected_targets for index in pair):
            self.history_pair_history_reject_events += 1
            return False
        if any(self.states[index] not in ("A", "C") for index in pair):
            self.history_pair_reject_events += 1
            return False
        if not self._virtual_pair_restores_committed_parity(pair):
            self.history_pair_virtual_parity_reject_events += 1
            return False

        for index in pair:
            self.protected_targets[index] = self._opposite(self.states[index])
        self.history_pair_decode_events += 1
        self.history_pair_added_targets += 2
        self.last_history_pair = pair
        self.max_repair_set_size = max(
            self.max_repair_set_size, len(self.protected_targets)
        )
        return True

    def _handoff_if_migrated(self) -> None:
        previous_handoffs = self.handoff_events
        previous_size = len(self.protected_targets)
        super()._handoff_if_migrated()

        # Ordinary W5/W6 semantics have priority. W8.3 is only a fallback for
        # a residual that those decoders could not resolve.
        if (
            self.handoff_events != previous_handoffs
            or len(self.protected_targets) != previous_size
        ):
            return
        self._history_pair_decode()
