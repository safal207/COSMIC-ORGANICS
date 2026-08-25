"""BARDO-EDGE-01 observational relation-field candidate.

The candidate receives exactly the same completed A/M/C transition facts as the
frozen conventional-edge control. It does not receive future target truth,
stronger evidence, or any authority to change MORPHOS dynamics.

The only candidate difference is organization: transition occurrences are
stored under a first-class relation key rather than treating the append-only
record list as the primary object. Canonical transition identities remain the
same TransitionRecord identities used by the conventional control.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from morphos.transition_edges import TransitionRecord, replay_transition_records
from morphos.witness_multierasure import MultiErasureAuthorityGrid2D


@dataclass(frozen=True)
class BardoRelation:
    """First-class relation identity for a local completed phase transition."""

    site: int
    from_phase: str
    to_phase: str
    source_site: int | None = None
    destination_site: int | None = None
    admissible: bool = True
    evidence_ref: str | None = None

    @classmethod
    def from_record(cls, record: TransitionRecord) -> "BardoRelation":
        return cls(
            site=record.site,
            from_phase=record.from_phase,
            to_phase=record.to_phase,
            source_site=record.source_site,
            destination_site=record.destination_site,
            admissible=record.admissible,
            evidence_ref=record.evidence_ref,
        )


class BardoEdgeFieldObserverGrid2D(MultiErasureAuthorityGrid2D):
    """W8.5 plus an observational relation-keyed transition field."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.edge_field: dict[BardoRelation, list[TransitionRecord]] = {}
        self._records_by_id: dict[str, TransitionRecord] = {}
        self._timeline: list[str] = []

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        before = tuple(self.states)
        super().step(stimulus)
        logical_tick = self.tick

        for site, (from_phase, to_phase) in enumerate(zip(before, self.states)):
            if from_phase == to_phase:
                continue
            record = TransitionRecord(
                site=site,
                from_phase=from_phase,
                to_phase=to_phase,
                logical_tick=logical_tick,
            )
            transition_id = record.transition_id
            if transition_id in self._records_by_id:
                raise RuntimeError("duplicate canonical transition identity")
            relation = BardoRelation.from_record(record)
            self.edge_field.setdefault(relation, []).append(record)
            self._records_by_id[transition_id] = record
            self._timeline.append(transition_id)

    @property
    def transition_records(self) -> tuple[TransitionRecord, ...]:
        return tuple(self._records_by_id[item] for item in self._timeline)

    def occurrences(self, relation: BardoRelation) -> tuple[TransitionRecord, ...]:
        return tuple(self.edge_field.get(relation, ()))

    def record_by_id(self, transition_id: str) -> TransitionRecord | None:
        return self._records_by_id.get(transition_id)

    def transition_metadata_bytes(self) -> int:
        return sum(len(record.canonical_bytes()) for record in self.transition_records)

    def replay(self, initial: str) -> str:
        return replay_transition_records(initial, self.transition_records)
