"""MORPHOS-M1 reflective state dynamics.

This is an algorithmic redundancy experiment, not a physical model of
consciousness, self-awareness, or quantum measurement.

The primary lattice carries the active state. A second internal mirror plane
stores the last locally stable self-image. The mirror is not supplied with a
target label or external oracle. It only updates after the primary state has
remained unchanged for a declared commit delay.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalGrid2D, HierarchicalLaw

_PHASES = ("A", "M", "C")
_VALUE = {"A": 0.0, "M": 0.5, "C": 1.0}


@dataclass(frozen=True)
class ReflectiveLaw:
    mirror_coupling: float = 0.15
    commit_delay: int = 3

    def __post_init__(self) -> None:
        if self.mirror_coupling < 0:
            raise ValueError("mirror_coupling must be non-negative")
        if self.commit_delay <= 0:
            raise ValueError("commit_delay must be positive")


class ReflectiveGrid2D(HierarchicalGrid2D):
    """HierarchicalGrid2D with a lagged internal self-image."""

    def __init__(
        self,
        initial: str,
        *,
        config: Grid2DConfig,
        law: HierarchicalLaw,
        reflective_law: ReflectiveLaw | None = None,
    ) -> None:
        super().__init__(initial, config=config, law=law)
        self.reflective_law = reflective_law or ReflectiveLaw()
        self.mirror_states = list(initial)
        self.stable_counts = [0] * len(initial)
        self.mirror_commits = 0

    @staticmethod
    def _flip_binary_phase(value: str) -> str:
        if value == "A":
            return "C"
        if value == "C":
            return "A"
        raise ValueError("binary perturbation requires A/C state")

    def perturb_primary(self, indices: Sequence[int]) -> None:
        for index in indices:
            if not 0 <= index < len(self.states):
                raise IndexError("primary perturbation index out of range")
            self.states[index] = self._flip_binary_phase(self.states[index])

    def perturb_mirror(self, indices: Sequence[int]) -> None:
        for index in indices:
            if not 0 <= index < len(self.mirror_states):
                raise IndexError("mirror perturbation index out of range")
            self.mirror_states[index] = self._flip_binary_phase(
                self.mirror_states[index]
            )

    def mirror_string(self) -> str:
        return "".join(self.mirror_states)

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        if isinstance(stimulus, (int, float)):
            stimuli = [float(stimulus)] * len(self.states)
        else:
            stimuli = [float(value) for value in stimulus]
            if len(stimuli) != len(self.states):
                raise ValueError("stimulus sequence length must equal cell count")

        previous_states = self.states.copy()
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

            mirror_delta = (
                _VALUE[self.mirror_states[index]] - _VALUE[phase]
            )
            drive = (
                stimuli[index]
                + coupling * weighted_delta
                + self.reflective_law.mirror_coupling * mirror_delta
            )
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

        for index, (before, after) in enumerate(
            zip(previous_states, self.states)
        ):
            if before == after:
                self.stable_counts[index] += 1
            else:
                self.stable_counts[index] = 0

            if (
                self.stable_counts[index]
                >= self.reflective_law.commit_delay
                and self.mirror_states[index] != after
            ):
                self.mirror_states[index] = after
                self.mirror_commits += 1
                self.stable_counts[index] = 0
