"""MORPHOS-M2 hierarchical reflective state dynamics.

This is an algorithmic redundancy experiment, not a physical model of
consciousness, self-awareness, or quantum measurement.

M2 extends M1 with three internal self-images that recommit at different
scales: per-cell, per-domain, and whole-system. No plane receives an external
target label after initialization; each can only be rewritten from primary
state that remains stable for its declared commit delay.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalGrid2D, HierarchicalLaw

_PHASES = ("A", "M", "C")
_VALUE = {"A": 0.0, "M": 0.5, "C": 1.0}


@dataclass(frozen=True)
class MultiReflectiveLaw:
    local_coupling: float = 0.15
    domain_coupling: float = 0.12
    system_coupling: float = 0.12
    local_commit_delay: int = 3
    domain_commit_delay: int = 4
    system_commit_delay: int = 5

    def __post_init__(self) -> None:
        for value in (
            self.local_coupling,
            self.domain_coupling,
            self.system_coupling,
        ):
            if value < 0:
                raise ValueError("mirror couplings must be non-negative")
        if not (
            0 < self.local_commit_delay
            < self.domain_commit_delay
            < self.system_commit_delay
        ):
            raise ValueError("commit delays must satisfy local < domain < system")


class MultiReflectiveGrid2D(HierarchicalGrid2D):
    """HierarchicalGrid2D with cell, domain, and system self-images."""

    def __init__(
        self,
        initial: str,
        *,
        config: Grid2DConfig,
        law: HierarchicalLaw,
        reflective_law: MultiReflectiveLaw | None = None,
    ) -> None:
        super().__init__(initial, config=config, law=law)
        self.reflective_law = reflective_law or MultiReflectiveLaw()
        self.local_mirror_states = list(initial)
        self.domain_mirror_states = list(initial)
        self.system_mirror_states = list(initial)
        self.local_stable_counts = [0] * len(initial)
        self.domain_stable_counts: dict[tuple[int, int], int] = {
            domain: 0 for domain in self._all_domains()
        }
        self.system_stable_count = 0
        self.local_mirror_commits = 0
        self.domain_mirror_commit_events = 0
        self.system_mirror_commit_events = 0

    @staticmethod
    def _flip_binary_phase(value: str) -> str:
        if value == "A":
            return "C"
        if value == "C":
            return "A"
        raise ValueError("binary perturbation requires A/C state")

    def _all_domains(self) -> list[tuple[int, int]]:
        return sorted({self._domain(i) for i in range(len(self.states))})

    def _domain_indices(self, domain: tuple[int, int]) -> list[int]:
        return [
            index
            for index in range(len(self.states))
            if self._domain(index) == domain
        ]

    def _perturb(self, plane: list[str], indices: Sequence[int]) -> None:
        for index in indices:
            if not 0 <= index < len(plane):
                raise IndexError("perturbation index out of range")
            plane[index] = self._flip_binary_phase(plane[index])

    def perturb_primary(self, indices: Sequence[int]) -> None:
        self._perturb(self.states, indices)

    def perturb_local_mirror(self, indices: Sequence[int]) -> None:
        self._perturb(self.local_mirror_states, indices)

    def perturb_domain_mirror(self, indices: Sequence[int]) -> None:
        self._perturb(self.domain_mirror_states, indices)

    def perturb_system_mirror(self, indices: Sequence[int]) -> None:
        self._perturb(self.system_mirror_states, indices)

    def local_mirror_string(self) -> str:
        return "".join(self.local_mirror_states)

    def domain_mirror_string(self) -> str:
        return "".join(self.domain_mirror_states)

    def system_mirror_string(self) -> str:
        return "".join(self.system_mirror_states)

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
        law = self.reflective_law

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

            local_delta = _VALUE[self.local_mirror_states[index]] - _VALUE[phase]
            domain_delta = _VALUE[self.domain_mirror_states[index]] - _VALUE[phase]
            system_delta = _VALUE[self.system_mirror_states[index]] - _VALUE[phase]
            drive = (
                stimuli[index]
                + coupling * weighted_delta
                + law.local_coupling * local_delta
                + law.domain_coupling * domain_delta
                + law.system_coupling * system_delta
            )
            activation = self.config.memory_decay * self.activations[index] + drive
            transition_threshold = (
                self.config.mixed_relax_threshold if phase == "M" else threshold
            )

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

        # Cell-level commits.
        for index, (before, after) in enumerate(zip(previous_states, self.states)):
            if before == after:
                self.local_stable_counts[index] += 1
            else:
                self.local_stable_counts[index] = 0
            if (
                self.local_stable_counts[index] >= law.local_commit_delay
                and self.local_mirror_states[index] != after
            ):
                self.local_mirror_states[index] = after
                self.local_mirror_commits += 1
                self.local_stable_counts[index] = 0

        # Domain-level commits require every primary cell in the domain to be
        # unchanged for the same tick sequence.
        for domain in self._all_domains():
            indices = self._domain_indices(domain)
            unchanged = all(previous_states[i] == self.states[i] for i in indices)
            self.domain_stable_counts[domain] = (
                self.domain_stable_counts[domain] + 1 if unchanged else 0
            )
            if self.domain_stable_counts[domain] >= law.domain_commit_delay:
                changed = False
                for index in indices:
                    if self.domain_mirror_states[index] != self.states[index]:
                        self.domain_mirror_states[index] = self.states[index]
                        changed = True
                if changed:
                    self.domain_mirror_commit_events += 1
                self.domain_stable_counts[domain] = 0

        # System-level commit requires the whole primary plane to be unchanged.
        if previous_states == self.states:
            self.system_stable_count += 1
        else:
            self.system_stable_count = 0
        if self.system_stable_count >= law.system_commit_delay:
            if self.system_mirror_states != self.states:
                self.system_mirror_states = self.states.copy()
                self.system_mirror_commit_events += 1
            self.system_stable_count = 0
