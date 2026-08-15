"""Deterministic local recurrent binary baseline for MORPHOS generalization."""
from __future__ import annotations


class RecurrentBinary2D:
    """Synchronous local recurrent threshold network over {-1,+1} states."""

    def __init__(
        self,
        initial: str,
        *,
        width: int,
        height: int,
        self_weight: float,
        neighbor_weight: float,
        neighborhood: str = "von_neumann",
    ) -> None:
        if len(initial) != width * height or any(value not in {"A", "C"} for value in initial):
            raise ValueError("RecurrentBinary2D requires a width*height binary A/C state")
        if self_weight < 0 or neighbor_weight <= 0:
            raise ValueError("weights must be non-negative / positive")
        if neighborhood not in {"von_neumann", "moore"}:
            raise ValueError("unsupported neighborhood")
        self.width = width
        self.height = height
        self.self_weight = float(self_weight)
        self.neighbor_weight = float(neighbor_weight)
        self.neighborhood = neighborhood
        self.states = [1.0 if value == "C" else -1.0 for value in initial]
        self.transitions = 0

    def _neighbors(self, index: int) -> list[int]:
        row, col = divmod(index, self.width)
        offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if self.neighborhood == "moore":
            offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        result: list[int] = []
        for dr, dc in offsets:
            rr, cc = row + dr, col + dc
            if 0 <= rr < self.height and 0 <= cc < self.width:
                result.append(rr * self.width + cc)
        return result

    def step(self) -> None:
        next_states = self.states.copy()
        for index, current in enumerate(self.states):
            neighbors = self._neighbors(index)
            neighbor_mean = sum(self.states[j] for j in neighbors) / len(neighbors)
            drive = self.self_weight * current + self.neighbor_weight * neighbor_mean
            if drive > 0:
                next_states[index] = 1.0
            elif drive < 0:
                next_states[index] = -1.0
            else:
                next_states[index] = current
        self.transitions += sum(a != b for a, b in zip(self.states, next_states))
        self.states = next_states

    def run(self, steps: int) -> None:
        for _ in range(steps):
            self.step()

    def state_string(self) -> str:
        return "".join("C" if value > 0 else "A" for value in self.states)
