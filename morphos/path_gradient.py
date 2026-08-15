"""MORPHOS-P1 path-gradient reflective dynamics.

P1 adds trajectory feedback to MORPHOS-M2 without adding an external target.
The model measures its distance from its own committed reflection hierarchy.
When that distance is non-improving, reflective coupling is temporarily
amplified for one transition step. When the path is already improving, the
base M2 dynamics are left unchanged.

This is an algorithmic toy model, not a model of consciousness or physics.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from morphos.grid2d import Grid2DConfig
from morphos.hierarchical import HierarchicalLaw
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw

_VALUE = {"A": 0.0, "M": 0.5, "C": 1.0}


@dataclass(frozen=True)
class PathGradientLaw:
    """Feedback applied only when reflection distance is not improving."""

    gradient_gain: float = 0.5
    epsilon: float = 1e-12

    def __post_init__(self) -> None:
        if self.gradient_gain < 0:
            raise ValueError("gradient_gain must be non-negative")
        if self.epsilon < 0:
            raise ValueError("epsilon must be non-negative")


class PathGradientGrid2D(MultiReflectiveGrid2D):
    """M2 with a one-step trajectory signal over internal reflection distance."""

    def __init__(
        self,
        initial: str,
        *,
        config: Grid2DConfig,
        law: HierarchicalLaw,
        reflective_law: MultiReflectiveLaw | None = None,
        path_law: PathGradientLaw | None = None,
    ) -> None:
        super().__init__(
            initial,
            config=config,
            law=law,
            reflective_law=reflective_law,
        )
        self.path_law = path_law or PathGradientLaw()
        # The system begins self-consistent. External perturbations occur after
        # construction, so the first divergent step can be recognized as moving
        # away from the last observed self-consistent state.
        self.previous_reflection_distance = 0.0
        self.last_reflection_distance = 0.0
        self.last_path_multiplier = 1.0
        self.boosted_steps = 0

    def reflection_distance(self) -> float:
        """Mean phase distance from primary to local/domain/system self-images."""

        total = 0.0
        comparisons = 0
        for primary, local, domain, system in zip(
            self.states,
            self.local_mirror_states,
            self.domain_mirror_states,
            self.system_mirror_states,
        ):
            p = _VALUE[primary]
            total += abs(p - _VALUE[local])
            total += abs(p - _VALUE[domain])
            total += abs(p - _VALUE[system])
            comparisons += 3
        return total / comparisons if comparisons else 0.0

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        current_distance = self.reflection_distance()
        epsilon = self.path_law.epsilon
        non_improving = (
            current_distance > epsilon
            and current_distance >= self.previous_reflection_distance - epsilon
        )
        multiplier = (
            1.0 + self.path_law.gradient_gain if non_improving else 1.0
        )

        base = self.reflective_law
        boosted = MultiReflectiveLaw(
            local_coupling=base.local_coupling * multiplier,
            domain_coupling=base.domain_coupling * multiplier,
            system_coupling=base.system_coupling * multiplier,
            local_commit_delay=base.local_commit_delay,
            domain_commit_delay=base.domain_commit_delay,
            system_commit_delay=base.system_commit_delay,
        )

        self.reflective_law = boosted
        try:
            super().step(stimulus)
        finally:
            self.reflective_law = base

        self.previous_reflection_distance = current_distance
        self.last_reflection_distance = self.reflection_distance()
        self.last_path_multiplier = multiplier
        if multiplier > 1.0:
            self.boosted_steps += 1
