"""Deterministic 2D heterogeneous MORPHOS lattice.

This is an algorithmic research model. Cell types, thresholds, masks, and
neighborhoods are not calibrated physical material parameters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

_PHASES = ("A", "M", "C")
_VALUE = {"A": 0.0, "M": 0.5, "C": 1.0}


@dataclass(frozen=True)
class Grid2DConfig:
    width: int = 5
    height: int = 5
    memory_decay: float = 0.0
    anchor_threshold: float = 0.5
    adaptive_threshold: float = 0.35
    anchor_coupling: float = 0.75
    adaptive_coupling: float = 0.5
    mixed_relax_threshold: float = 0.05
    mask: str = "checkerboard"
    neighborhood: str = "von_neumann"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if not 0.0 <= self.memory_decay <= 1.0:
            raise ValueError("memory_decay must be between 0 and 1")
        for value in (
            self.anchor_threshold,
            self.adaptive_threshold,
            self.mixed_relax_threshold,
        ):
            if value <= 0:
                raise ValueError("thresholds must be positive")
        for value in (self.anchor_coupling, self.adaptive_coupling):
            if value < 0:
                raise ValueError("couplings must be non-negative")
        if self.mask not in {"checkerboard", "row_stripes", "column_stripes", "quadrants"}:
            raise ValueError("unsupported mask")
        if self.neighborhood not in {"von_neumann", "moore"}:
            raise ValueError("unsupported neighborhood")


class Grid2D:
    """Synchronous A/M/C lattice with two declared cell classes."""

    def __init__(self, initial: str, *, config: Grid2DConfig | None = None) -> None:
        self.config = config or Grid2DConfig()
        expected = self.config.width * self.config.height
        if len(initial) != expected:
            raise ValueError("initial state length must equal width * height")
        if any(value not in _PHASES for value in initial):
            raise ValueError("initial state must contain only A/M/C")
        self.states = list(initial)
        self.activations = [0.0] * expected
        self.transitions = 0
        self.tick = 0

    def _neighbors(self, index: int) -> list[int]:
        row, col = divmod(index, self.config.width)
        offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if self.config.neighborhood == "moore":
            offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        neighbors: list[int] = []
        for dr, dc in offsets:
            rr, cc = row + dr, col + dc
            if 0 <= rr < self.config.height and 0 <= cc < self.config.width:
                neighbors.append(rr * self.config.width + cc)
        return neighbors

    def _is_anchor(self, index: int) -> bool:
        row, col = divmod(index, self.config.width)
        if self.config.mask == "checkerboard":
            return (row + col) % 2 == 0
        if self.config.mask == "row_stripes":
            return row % 2 == 0
        if self.config.mask == "column_stripes":
            return col % 2 == 0
        return (row < self.config.height // 2) == (col < self.config.width // 2)

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        if isinstance(stimulus, (int, float)):
            stimuli = [float(stimulus)] * len(self.states)
        else:
            stimuli = [float(value) for value in stimulus]
            if len(stimuli) != len(self.states):
                raise ValueError("stimulus sequence length must equal cell count")

        next_states = self.states.copy()
        next_activations = self.activations.copy()

        for index, phase in enumerate(self.states):
            anchor = self._is_anchor(index)
            threshold = self.config.anchor_threshold if anchor else self.config.adaptive_threshold
            coupling = self.config.anchor_coupling if anchor else self.config.adaptive_coupling
            neighbors = self._neighbors(index)
            neighbor_mean = sum(_VALUE[self.states[j]] for j in neighbors) / len(neighbors)
            drive = stimuli[index] + coupling * (neighbor_mean - _VALUE[phase])
            activation = self.config.memory_decay * self.activations[index] + drive

            transition_threshold = self.config.mixed_relax_threshold if phase == "M" else threshold
            direction = 0
            if activation >= transition_threshold:
                direction = 1
            elif activation <= -transition_threshold:
                direction = -1

            phase_index = _PHASES.index(phase)
            next_index = max(0, min(len(_PHASES) - 1, phase_index + direction))
            next_phase = _PHASES[next_index]
            if next_phase != phase:
                self.transitions += 1
                activation = 0.0

            next_states[index] = next_phase
            next_activations[index] = activation

        self.states = next_states
        self.activations = next_activations
        self.tick += 1

    def run(self, pulses: Iterable[float | Sequence[float]]) -> None:
        for pulse in pulses:
            self.step(pulse)

    def state_string(self) -> str:
        return "".join(self.states)

    def rows(self) -> list[str]:
        return [
            "".join(self.states[start : start + self.config.width])
            for start in range(0, len(self.states), self.config.width)
        ]
