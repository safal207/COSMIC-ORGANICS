"""BARDO-FRONTIER-02 controls for exact sparse scheduling.

This module contains only the dense reference and the strong conventional
DIRTY_NODE scheduler. The BARDO_FRONTIER candidate is intentionally absent
until the preregistration/control boundary is frozen.

Sparse skipping is valid only for the preregistered Grid2D surface with
memory_decay == 0.0 and a quiescent (zero-stimulus fixed-point) start. Under
those conditions a node must be reevaluated only when its external stimulus
changes or when its own/neighbor phase changed on the previous logical tick.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from morphos.grid2d import Grid2D, Grid2DConfig, _PHASES, _VALUE


@dataclass(frozen=True)
class SchedulerCounters:
    node_evaluations: int
    scheduled_work_items: int
    stimulus_change_insert_attempts: int
    frontier_insert_attempts: int
    dedup_hits: int
    state_writes: int
    transition_records_emitted: int


class InstrumentedDenseGrid2D(Grid2D):
    """Frozen dense reference with operation counters only."""

    def __init__(self, initial: str, *, config: Grid2DConfig) -> None:
        super().__init__(initial, config=config)
        self.node_evaluations = 0
        self.scheduled_work_items = 0
        self.stimulus_change_insert_attempts = 0
        self.frontier_insert_attempts = 0
        self.dedup_hits = 0
        self.state_writes = 0
        self.transition_records_emitted = 0

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        before = tuple(self.states)
        transitions_before = self.transitions
        cells = len(self.states)
        self.node_evaluations += cells
        self.scheduled_work_items += cells
        super().step(stimulus)
        changed = sum(a != b for a, b in zip(before, self.states))
        if changed != self.transitions - transitions_before:
            raise RuntimeError("dense transition counter diverged from state delta")
        self.state_writes += changed
        self.transition_records_emitted += changed

    @property
    def unchanged_node_evaluations_avoided(self) -> int:
        return 0

    def scheduler_counters(self) -> SchedulerCounters:
        return SchedulerCounters(
            node_evaluations=self.node_evaluations,
            scheduled_work_items=self.scheduled_work_items,
            stimulus_change_insert_attempts=self.stimulus_change_insert_attempts,
            frontier_insert_attempts=self.frontier_insert_attempts,
            dedup_hits=self.dedup_hits,
            state_writes=self.state_writes,
            transition_records_emitted=self.transition_records_emitted,
        )


class DirtyNodeGrid2D(Grid2D):
    """Strong deterministic dirty-node control preserving synchronous semantics."""

    def __init__(self, initial: str, *, config: Grid2DConfig) -> None:
        if config.memory_decay != 0.0:
            raise ValueError("DIRTY_NODE preregistration requires memory_decay == 0")
        super().__init__(initial, config=config)
        self._dirty_next: set[int] = set()
        self._previous_stimuli = [0.0] * len(self.states)
        self.node_evaluations = 0
        self.scheduled_work_items = 0
        self.stimulus_change_insert_attempts = 0
        self.frontier_insert_attempts = 0
        self.dedup_hits = 0
        self.state_writes = 0
        self.transition_records_emitted = 0

    def _stimuli(self, stimulus: float | Sequence[float]) -> list[float]:
        if isinstance(stimulus, (int, float)):
            return [float(stimulus)] * len(self.states)
        values = [float(value) for value in stimulus]
        if len(values) != len(self.states):
            raise ValueError("stimulus sequence length must equal cell count")
        return values

    @staticmethod
    def _insert(target: set[int], item: int) -> bool:
        before = len(target)
        target.add(item)
        return len(target) == before

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        stimuli = self._stimuli(stimulus)
        scheduled: set[int] = set()

        for index in sorted(self._dirty_next):
            self.frontier_insert_attempts += 1
            if self._insert(scheduled, index):
                self.dedup_hits += 1

        for index, (previous, current) in enumerate(
            zip(self._previous_stimuli, stimuli)
        ):
            if previous == current:
                continue
            self.stimulus_change_insert_attempts += 1
            if self._insert(scheduled, index):
                self.dedup_hits += 1

        ordered = sorted(scheduled)
        self.node_evaluations += len(ordered)
        self.scheduled_work_items += len(ordered)

        next_states = self.states.copy()
        next_activations = self.activations.copy()
        changed: list[int] = []

        for index in ordered:
            phase = self.states[index]
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
            neighbor_mean = (
                sum(_VALUE[self.states[j]] for j in neighbors) / len(neighbors)
            )
            drive = stimuli[index] + coupling * (
                neighbor_mean - _VALUE[phase]
            )
            activation = drive  # memory_decay is frozen to zero.

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
                changed.append(index)
                self.transitions += 1
                activation = 0.0

            next_states[index] = next_phase
            next_activations[index] = activation

        dirty_next: set[int] = set()
        for index in changed:
            for item in (index, *self._neighbors(index)):
                self.frontier_insert_attempts += 1
                if self._insert(dirty_next, item):
                    self.dedup_hits += 1

        self.states = next_states
        self.activations = next_activations
        self._dirty_next = dirty_next
        self._previous_stimuli = stimuli
        self.state_writes += len(changed)
        self.transition_records_emitted += len(changed)
        self.tick += 1

    @property
    def unchanged_node_evaluations_avoided(self) -> int:
        dense_equivalent = self.tick * len(self.states)
        return dense_equivalent - self.node_evaluations

    def scheduler_counters(self) -> SchedulerCounters:
        return SchedulerCounters(
            node_evaluations=self.node_evaluations,
            scheduled_work_items=self.scheduled_work_items,
            stimulus_change_insert_attempts=self.stimulus_change_insert_attempts,
            frontier_insert_attempts=self.frontier_insert_attempts,
            dedup_hits=self.dedup_hits,
            state_writes=self.state_writes,
            transition_records_emitted=self.transition_records_emitted,
        )
