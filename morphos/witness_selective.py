"""MORPHOS-W4 selective witness-validated authority fence.

W4 keeps healthy mirror evidence active and suppresses only mirror contributions
that contradict the independently witnessed endpoint at the localized repair
cell. The repair transaction remains open until the target cell and its three
mirror values have recommitted to the witness-consistent endpoint.

This is a classical algorithmic recovery experiment, not quantum error
correction and not a physical material implementation.
"""
from __future__ import annotations

from typing import Sequence

from morphos.multimirror import MultiReflectiveGrid2D
from morphos.witness import IndependentWitnessGrid2D
from morphos.witness_persistent import PersistentWitnessGrid2D

_PHASES = ("A", "M", "C")
_VALUE = {"A": 0.0, "M": 0.5, "C": 1.0}


class SelectiveAuthorityGrid2D(PersistentWitnessGrid2D):
    """Quarantine only mirror claims that contradict the latched endpoint."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.selective_fence_active = False
        self.fence_open_events = 0
        self.fence_release_events = 0
        self.fence_abort_for_stimulus_events = 0
        self.suppressed_mirror_contributions = 0
        self.preserved_mirror_contributions = 0

    @staticmethod
    def _normalize_stimulus(
        stimulus: float | Sequence[float], count: int
    ) -> list[float]:
        if isinstance(stimulus, (int, float)):
            return [float(stimulus)] * count
        values = [float(value) for value in stimulus]
        if len(values) != count:
            raise ValueError("stimulus sequence length must equal cell count")
        return values

    @staticmethod
    def _quiescent(stimuli: Sequence[float]) -> bool:
        return all(abs(value) <= 1e-12 for value in stimuli)

    def _open_fence_if_localized(self) -> None:
        if self.selective_fence_active or self.witness_law.witness_drive <= 0:
            return
        self._maybe_latch_from_syndrome()
        if self.latched_index is not None:
            self.selective_fence_active = True
            self.fence_open_events += 1

    def _mirror_drive(
        self,
        *,
        index: int,
        phase: str,
        mirror_phase: str,
        coupling: float,
    ) -> float:
        delta = _VALUE[mirror_phase] - _VALUE[phase]
        if (
            self.selective_fence_active
            and self.latched_index == index
            and self.latched_target is not None
        ):
            if mirror_phase != self.latched_target:
                self.suppressed_mirror_contributions += 1
                return 0.0
            self.preserved_mirror_contributions += 1
        return coupling * delta

    def _target_mirrors_agree(self) -> bool:
        if self.latched_index is None or self.latched_target is None:
            return False
        index = self.latched_index
        target = self.latched_target
        return (
            self.local_mirror_states[index] == target
            and self.domain_mirror_states[index] == target
            and self.system_mirror_states[index] == target
        )

    def _release_fence_if_committed(self) -> None:
        if (
            not self.selective_fence_active
            or self.latched_index is None
            or self.latched_target is None
        ):
            return
        target_reached = self.states[self.latched_index] == self.latched_target
        witness_agrees = self.syndrome() == ((), ())
        if target_reached and witness_agrees and self._target_mirrors_agree():
            self.selective_fence_active = False
            self.latched_index = None
            self.latched_target = None
            self.latch_clear_events += 1
            self.fence_release_events += 1

    def _transition_and_commit(self, stimuli: list[float]) -> None:
        previous_states = self.states.copy()
        next_states = self.states.copy()
        next_activations = self.activations.copy()
        intra_factor = self.law.intra_factor(
            self.config.width, self.config.height
        )
        mirror_law = self.reflective_law

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

            mirror_drive = (
                self._mirror_drive(
                    index=index,
                    phase=phase,
                    mirror_phase=self.local_mirror_states[index],
                    coupling=mirror_law.local_coupling,
                )
                + self._mirror_drive(
                    index=index,
                    phase=phase,
                    mirror_phase=self.domain_mirror_states[index],
                    coupling=mirror_law.domain_coupling,
                )
                + self._mirror_drive(
                    index=index,
                    phase=phase,
                    mirror_phase=self.system_mirror_states[index],
                    coupling=mirror_law.system_coupling,
                )
            )
            drive = stimuli[index] + coupling * weighted_delta + mirror_drive
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

        # Preserve M2 recommit semantics while authority is filtered only at
        # the localized cell.
        for index, (before, after) in enumerate(zip(previous_states, self.states)):
            if before == after:
                self.local_stable_counts[index] += 1
            else:
                self.local_stable_counts[index] = 0
            if (
                self.local_stable_counts[index] >= mirror_law.local_commit_delay
                and self.local_mirror_states[index] != after
            ):
                self.local_mirror_states[index] = after
                self.local_mirror_commits += 1
                self.local_stable_counts[index] = 0

        for domain in self._all_domains():
            indices = self._domain_indices(domain)
            unchanged = all(previous_states[i] == self.states[i] for i in indices)
            self.domain_stable_counts[domain] = (
                self.domain_stable_counts[domain] + 1 if unchanged else 0
            )
            if self.domain_stable_counts[domain] >= mirror_law.domain_commit_delay:
                changed = False
                for index in indices:
                    if self.domain_mirror_states[index] != self.states[index]:
                        self.domain_mirror_states[index] = self.states[index]
                        changed = True
                if changed:
                    self.domain_mirror_commit_events += 1
                self.domain_stable_counts[domain] = 0

        if previous_states == self.states:
            self.system_stable_count += 1
        else:
            self.system_stable_count = 0
        if self.system_stable_count >= mirror_law.system_commit_delay:
            if self.system_mirror_states != self.states:
                self.system_mirror_states = self.states.copy()
                self.system_mirror_commit_events += 1
            self.system_stable_count = 0

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        stimuli = self._normalize_stimulus(stimulus, len(self.states))

        # Explicit non-zero input is treated as an intended transition request,
        # not a quiescent repair transaction.
        if not self._quiescent(stimuli):
            if self.selective_fence_active:
                self.selective_fence_active = False
                self.latched_index = None
                self.latched_target = None
                self.fence_abort_for_stimulus_events += 1
            IndependentWitnessGrid2D.step(self, stimuli)
            return

        previous_primary = self.state_string()
        syndrome = self.syndrome()
        self.last_syndrome = syndrome
        self.last_localized_index = self.localized_error_index()
        if syndrome != ((), ()):
            self.syndrome_events += 1

        self._open_fence_if_localized()
        if self.selective_fence_active:
            self.localized_events += 1
            self._apply_latched_drive(stimuli)

        self._transition_and_commit(stimuli)
        self._release_fence_if_committed()

        # Do not rewrite the independent witness from an uncommitted repair.
        if not self.selective_fence_active:
            self._update_witness_commit(previous_primary, self.state_string())
