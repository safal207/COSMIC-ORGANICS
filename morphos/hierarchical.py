"""MORPHOS-S2 hierarchical scale coupling.

This is an algorithmic research mechanism, not a calibrated physical law.
It preserves the MORPHOS-S1 global scale law and adds a second interaction
scale: same-domain nearest-neighbor edges can strengthen with lattice size
while cross-domain edges remain at the S1 coupling level.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from morphos.grid2d import Grid2D, Grid2DConfig

_PHASES = ("A", "M", "C")
_VALUE = {"A": 0.0, "M": 0.5, "C": 1.0}


@dataclass(frozen=True)
class HierarchicalLaw:
    reference_linear_size: float = 5.0
    exponent: float = 0.06
    domain_size: int = 3

    def __post_init__(self) -> None:
        if self.reference_linear_size <= 0:
            raise ValueError("reference_linear_size must be positive")
        if self.exponent < 0:
            raise ValueError("exponent must be non-negative")
        if self.domain_size <= 0:
            raise ValueError("domain_size must be positive")

    def intra_factor(self, width: int, height: int) -> float:
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        linear_size = float(max(width, height))
        return (linear_size / self.reference_linear_size) ** self.exponent


class HierarchicalGrid2D(Grid2D):
    """Grid2D with a second, local-domain interaction scale."""

    def __init__(
        self,
        initial: str,
        *,
        config: Grid2DConfig,
        law: HierarchicalLaw,
    ) -> None:
        super().__init__(initial, config=config)
        self.law = law

    def _domain(self, index: int) -> tuple[int, int]:
        row, col = divmod(index, self.config.width)
        return row // self.law.domain_size, col // self.law.domain_size

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        if isinstance(stimulus, (int, float)):
            stimuli = [float(stimulus)] * len(self.states)
        else:
            stimuli = [float(value) for value in stimulus]
            if len(stimuli) != len(self.states):
                raise ValueError("stimulus sequence length must equal cell count")

        next_states = self.states.copy()
        next_activations = self.activations.copy()
        intra_factor = self.law.intra_factor(
            self.config.width, self.config.height
        )

        for index, phase in enumerate(self.states):
            anchor = self._is_anchor(index)
            threshold = (
                self.config.anchor_threshold
                if anchor
                else self.config.adaptive_threshold
            )
            coupling = (
                self.config.anchor_coupling
                if anchor
                else self.config.adaptive_coupling
            )
            neighbors = self._neighbors(index)
            domain = self._domain(index)
            weighted_delta = sum(
                (
                    intra_factor
                    if self._domain(neighbor) == domain
                    else 1.0
                )
                * (_VALUE[self.states[neighbor]] - _VALUE[phase])
                for neighbor in neighbors
            ) / len(neighbors)

            drive = stimuli[index] + coupling * weighted_delta
            activation = (
                self.config.memory_decay * self.activations[index] + drive
            )
            transition_threshold = (
                self.config.mixed_relax_threshold
                if phase == "M"
                else threshold
            )

            direction = 0
            if activation >= transition_threshold:
                direction = 1
            elif activation <= -transition_threshold:
                direction = -1

            phase_index = _PHASES.index(phase)
            next_index = max(
                0, min(len(_PHASES) - 1, phase_index + direction)
            )
            next_phase = _PHASES[next_index]
            if next_phase != phase:
                self.transitions += 1
                activation = 0.0

            next_states[index] = next_phase
            next_activations[index] = activation

        self.states = next_states
        self.activations = next_activations
        self.tick += 1
