"""BARDO-FRONTIER-02 relation-native sparse scheduler candidate.

The candidate preserves the frozen Grid2D transition law exactly. Its only
architectural difference from DIRTY_NODE is that pending work is represented as
first-class influence relations and node evaluation is derived from relation
destinations. It receives no future state truth or stronger transition rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from morphos.grid2d import Grid2D, Grid2DConfig, _PHASES, _VALUE
from morphos.sparse_scheduler import SchedulerCounters


@dataclass(frozen=True, order=True)
class FrontierRelation:
    """A first-class causal scheduling relation."""

    source_site: int | None
    destination_site: int
    cause: str

    def __post_init__(self) -> None:
        if self.source_site is not None and self.source_site < 0:
            raise ValueError("source_site must be non-negative")
        if self.destination_site < 0:
            raise ValueError("destination_site must be non-negative")
        if self.cause not in {"phase_change", "stimulus_change"}:
            raise ValueError("unsupported frontier cause")


class BardoFrontierGrid2D(Grid2D):
    """Exact synchronous Grid2D scheduled from relation destinations."""

    def __init__(self, initial: str, *, config: Grid2DConfig) -> None:
        if config.memory_decay != 0.0:
            raise ValueError("BARDO_FRONTIER preregistration requires memory_decay == 0")
        super().__init__(initial, config=config)
        self._frontier_next: set[FrontierRelation] = set()
        self._previous_stimuli = [0.0] * len(self.states)
        self.node_evaluations = 0
        self.scheduled_work_items = 0
        self.stimulus_change_insert_attempts = 0
        self.frontier_insert_attempts = 0
        self.dedup_hits = 0
        self.state_writes = 0
        self.transition_records_emitted = 0
        self.relation_evaluations = 0

    def _stimuli(self, stimulus: float | Sequence[float]) -> list[float]:
        if isinstance(stimulus, (int, float)):
            return [float(stimulus)] * len(self.states)
        values = [float(value) for value in stimulus]
        if len(values) != len(self.states):
            raise ValueError("stimulus sequence length must equal cell count")
        return values

    def _insert_relation(
        self, target: set[FrontierRelation], relation: FrontierRelation
    ) -> None:
        self.frontier_insert_attempts += 1
        before = len(target)
        target.add(relation)
        if len(target) == before:
            self.dedup_hits += 1

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        stimuli = self._stimuli(stimulus)
        active_relations = set(self._frontier_next)

        for index, (previous, current) in enumerate(
            zip(self._previous_stimuli, stimuli)
        ):
            if previous == current:
                continue
            self.stimulus_change_insert_attempts += 1
            self._insert_relation(
                active_relations,
                FrontierRelation(None, index, "stimulus_change"),
            )

        self.relation_evaluations += len(active_relations)
        destinations = {relation.destination_site for relation in active_relations}
        ordered = sorted(destinations)
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
            activation = drive

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

        frontier_next: set[FrontierRelation] = set()
        for source in changed:
            self._insert_relation(
                frontier_next,
                FrontierRelation(source, source, "phase_change"),
            )
            for destination in self._neighbors(source):
                self._insert_relation(
                    frontier_next,
                    FrontierRelation(source, destination, "phase_change"),
                )

        self.states = next_states
        self.activations = next_activations
        self._frontier_next = frontier_next
        self._previous_stimuli = stimuli
        self.state_writes += len(changed)
        self.transition_records_emitted += len(changed)
        self.tick += 1

    @property
    def unchanged_node_evaluations_avoided(self) -> int:
        dense_equivalent = self.tick * len(self.states)
        return dense_equivalent - self.node_evaluations

    @property
    def frontier_size(self) -> int:
        return len(self._frontier_next)

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
