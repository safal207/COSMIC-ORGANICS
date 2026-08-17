"""MORPHOS-W8.2 executable margin closure.

W8.1 computes the mathematically minimal deficit needed to cross an existing
transition threshold. A frozen numeric diagnostic showed one residual where
materializing that deficit into the actual floating-point ``stimulus`` leaves
the executed transition predicate one representable step below threshold.

W8.2 does not add an epsilon, change a threshold, or raise witness amplitude.
It lets W8.1 realize its analytic completion first, then evaluates the exact
transition predicate from the realized control value. If that predicate still
fails, W8.2 advances the *control variable itself* by one ``nextafter`` step in
the witnessed direction and re-evaluates, stopping at the first representable
stimulus whose executed predicate passes.

The authority scope is unchanged from W8.1: quiescent repair, active selective
fence, exactly one initial protected obligation, and no post-handoff repair-set
expansion. This is a classical deterministic software/control experiment, not
a physical-energy, quantum, biological, or hardware-validity claim.
"""
from __future__ import annotations

import math

from morphos.witness_path_completion import PathCompletionAuthorityGrid2D
from morphos.witness_selective import _VALUE


class ExecutableMarginClosureGrid2D(PathCompletionAuthorityGrid2D):
    """Close W8.1's margin in the executable floating-point control space."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.executable_closure_events = 0
        self.executable_closure_steps = 0
        self.executable_closure_total = 0.0
        self.executable_closure_max_steps = 0

    def _actual_toward_target(
        self, *, index: int, phase: str, target: str, stimulus_value: float
    ) -> tuple[float, float]:
        """Return the exact transition-side predicate value and threshold.

        The arithmetic order intentionally matches ``_transition_and_commit``:
        memory term + realized stimulus + coupled neighborhood + mirror drive.
        """
        anchor = self._is_anchor(index)
        threshold = (
            self.config.mixed_relax_threshold
            if phase == "M"
            else (
                self.config.anchor_threshold
                if anchor
                else self.config.adaptive_threshold
            )
        )
        coupling = (
            self.config.anchor_coupling if anchor else self.config.adaptive_coupling
        )
        neighbors = self._neighbors(index)
        domain = self._domain(index)
        intra_factor = self.law.intra_factor(
            self.config.width, self.config.height
        )
        weighted_delta = sum(
            (intra_factor if self._domain(neighbor) == domain else 1.0)
            * (_VALUE[self.states[neighbor]] - _VALUE[phase])
            for neighbor in neighbors
        ) / len(neighbors)
        mirror_drive = self._effective_protected_mirror_drive(
            index=index, phase=phase, target=target
        )
        activation = (
            self.config.memory_decay * self.activations[index]
            + stimulus_value
            + coupling * weighted_delta
            + mirror_drive
        )
        direction = 1.0 if target == "C" else -1.0
        return direction * activation, threshold

    def _closure_eligible(self) -> tuple[int, str, str] | None:
        if (
            not self.selective_fence_active
            or len(self.protected_targets) != 1
            or self.latched_index is None
            or self.latched_target not in ("A", "C")
        ):
            return None
        index = self.latched_index
        target = self.latched_target
        if self.protected_targets.get(index) != target:
            return None
        phase = self.states[index]
        if phase == target:
            return None
        if phase == "A" and target != "C":
            return None
        if phase == "C" and target != "A":
            return None
        if phase not in ("A", "M", "C"):
            return None
        return index, phase, target

    def _entry_margin_completion(self, stimuli: list[float]) -> None:
        # Preserve the complete frozen W8.1 mechanism first.
        super()._entry_margin_completion(stimuli)

        eligible = self._closure_eligible()
        if eligible is None:
            return
        index, phase, target = eligible
        toward, threshold = self._actual_toward_target(
            index=index,
            phase=phase,
            target=target,
            stimulus_value=stimuli[index],
        )
        if toward >= threshold:
            return

        direction = 1.0 if target == "C" else -1.0
        next_direction = math.inf if direction > 0 else -math.inf
        starting_stimulus = stimuli[index]
        steps = 0

        # Search in the actual representable control space. There is no
        # user-tunable epsilon: each iteration advances exactly one float.
        while toward < threshold:
            previous = stimuli[index]
            candidate = math.nextafter(previous, next_direction)
            if candidate == previous:
                raise RuntimeError(
                    "no representable stimulus can advance the transition predicate"
                )
            stimuli[index] = candidate
            steps += 1
            toward, threshold = self._actual_toward_target(
                index=index,
                phase=phase,
                target=target,
                stimulus_value=candidate,
            )

        self.executable_closure_events += 1
        self.executable_closure_steps += steps
        self.executable_closure_total += abs(stimuli[index] - starting_stimulus)
        self.executable_closure_max_steps = max(
            self.executable_closure_max_steps, steps
        )
