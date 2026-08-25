"""MORPHOS-W8.5 transition-state GF(2) handoff.

W8.4 fresh diagnostics showed a binary-observability delay when exactly two
unresolved cells simultaneously occupy MORPHOS's transition state ``M`` after
the original protected source has already reached its witnessed endpoint.
A separate global safety scan over 1728 observed trials found that a narrow
runtime predicate was uniquely solvable and diagnostically correct everywhere
it activated: one verified source, exactly two unprotected ``M`` cells, a
unique row/column-parity solution over GF(2), and complete virtual committed-
parity replay.

W8.5 adds observability/ownership only. After W5/W6/W8.3/W8.4 have made no
ownership expansion, it may infer the two ``M`` endpoint bits under that exact
predicate and add both obligations to W7's existing ``protected_targets``.
W7 then supplies its unchanged bounded witness drive to the enlarged repair set.

No amplitude, transition threshold, coupling, parity code, commit delay, or
horizon is changed. Ambiguous, inconsistent, >2-M, zero-witness, and
unverified-source states fail closed. This is a classical deterministic
software/control experiment, not quantum error correction or a physical model.
"""
from __future__ import annotations

from morphos.witness_causal_locality import CausalLocalityAuthorityGrid2D


class MultiErasureAuthorityGrid2D(CausalLocalityAuthorityGrid2D):
    """Infer exactly two transition-state endpoint bits from committed parity."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.multi_erasure_decode_events = 0
        self.multi_erasure_added_targets = 0
        self.multi_erasure_reject_events = 0
        self.multi_erasure_ambiguous_events = 0
        self.multi_erasure_inconsistent_events = 0
        self.last_multi_erasure_indices: tuple[int, int] | None = None
        self.last_multi_erasure_targets: tuple[str, str] | None = None

    @staticmethod
    def _gf2_solve(
        matrix: list[list[int]], rhs: list[int], variables: int
    ) -> tuple[str, list[int] | None]:
        """Gauss-Jordan solve over GF(2)."""
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
                return "no_solution", None

        if len(pivot_cols) < variables:
            return "multiple_solutions", None

        solution = [0] * variables
        for r, col in enumerate(pivot_cols):
            solution[col] = aug[r][variables]
        return "unique_solution", solution

    def _multi_erasure_equations(
        self, unknowns: tuple[int, int]
    ) -> tuple[list[list[int]], list[int]]:
        index_of = {cell: i for i, cell in enumerate(unknowns)}
        matrix: list[list[int]] = []
        rhs: list[int] = []
        width = self.config.width
        height = self.config.height

        for row in range(height):
            coeff = [0, 0]
            known_xor = 0
            for col in range(width):
                index = row * width + col
                if index in index_of:
                    coeff[index_of[index]] ^= 1
                else:
                    value = self.states[index]
                    if value not in ("A", "C"):
                        raise ValueError(
                            "multi-erasure equations require exactly two M states"
                        )
                    known_xor ^= self._bit(value)
            matrix.append(coeff)
            rhs.append(self.row_parity[row] ^ known_xor)

        for col in range(width):
            coeff = [0, 0]
            known_xor = 0
            for row in range(height):
                index = row * width + col
                if index in index_of:
                    coeff[index_of[index]] ^= 1
                else:
                    value = self.states[index]
                    if value not in ("A", "C"):
                        raise ValueError(
                            "multi-erasure equations require exactly two M states"
                        )
                    known_xor ^= self._bit(value)
            matrix.append(coeff)
            rhs.append(self.column_parity[col] ^ known_xor)

        return matrix, rhs

    def _multi_erasure_virtual_parity_ok(
        self, unknowns: tuple[int, int], bits: list[int]
    ) -> bool:
        virtual = self.states.copy()
        for index, bit in zip(unknowns, bits):
            virtual[index] = "C" if bit else "A"
        rows, columns = self._parity("".join(virtual))
        return rows == self.row_parity and columns == self.column_parity

    def _multi_erasure_decode(self) -> bool:
        if (
            not self.selective_fence_active
            or self.witness_law.witness_drive <= 0
            or self.latched_index is None
            or self.latched_target not in ("A", "C")
            or len(self.protected_targets) != 1
        ):
            return False

        source = self.latched_index
        if (
            self.protected_targets.get(source) != self.latched_target
            or self.states[source] != self.latched_target
        ):
            return False

        unknowns = tuple(
            index for index, phase in enumerate(self.states) if phase == "M"
        )
        if len(unknowns) != 2:
            return False
        if any(index in self.protected_targets for index in unknowns):
            return False

        try:
            matrix, rhs = self._multi_erasure_equations(unknowns)
        except ValueError:
            self.multi_erasure_reject_events += 1
            return False

        status, bits = self._gf2_solve(matrix, rhs, 2)
        if status == "multiple_solutions":
            self.multi_erasure_ambiguous_events += 1
            return False
        if status == "no_solution" or bits is None:
            self.multi_erasure_inconsistent_events += 1
            return False
        if not self._multi_erasure_virtual_parity_ok(unknowns, bits):
            self.multi_erasure_reject_events += 1
            return False

        endpoints = tuple("C" if bit else "A" for bit in bits)
        for index, endpoint in zip(unknowns, endpoints):
            self.protected_targets[index] = endpoint

        self.multi_erasure_decode_events += 1
        self.multi_erasure_added_targets += 2
        self.last_multi_erasure_indices = unknowns
        self.last_multi_erasure_targets = endpoints
        self.max_repair_set_size = max(
            self.max_repair_set_size, len(self.protected_targets)
        )
        return True

    def _handoff_if_migrated(self) -> None:
        previous_handoffs = self.handoff_events
        previous_history = self.history_pair_decode_events
        previous_locality = self.locality_pair_decode_events
        previous_size = len(self.protected_targets)
        super()._handoff_if_migrated()

        # W5/W6/W8.3/W8.4 have strict priority. Multi-M inference is the final
        # fallback only if no earlier decoder changed ownership or repair set.
        if (
            self.handoff_events != previous_handoffs
            or self.history_pair_decode_events != previous_history
            or self.locality_pair_decode_events != previous_locality
            or len(self.protected_targets) != previous_size
        ):
            return
        self._multi_erasure_decode()
