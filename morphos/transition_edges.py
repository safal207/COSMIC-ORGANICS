"""BARDO-EDGE-01 controls: explicit observational transition events.

This module intentionally implements only the strong conventional explicit-edge
control frozen by BARDO-EDGE-01.  It is observational: it may record completed
A/M/C phase changes but cannot influence MORPHOS dynamics, repair ownership, or
witness authority.

The Bardo candidate is deliberately absent from this file.  Controls are frozen
first so the candidate cannot redefine the baseline after results are observed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Sequence

from morphos.witness_multierasure import MultiErasureAuthorityGrid2D


@dataclass(frozen=True)
class TransitionRecord:
    """Canonical observational record for one completed local phase change."""

    site: int
    from_phase: str
    to_phase: str
    logical_tick: int
    source_site: int | None = None
    destination_site: int | None = None
    admissible: bool = True
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        if self.site < 0:
            raise ValueError("site must be non-negative")
        if self.from_phase not in {"A", "M", "C"}:
            raise ValueError("unsupported from_phase")
        if self.to_phase not in {"A", "M", "C"}:
            raise ValueError("unsupported to_phase")
        if self.from_phase == self.to_phase:
            raise ValueError("transition record requires a phase change")
        if self.logical_tick <= 0:
            raise ValueError("logical_tick must be positive")

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")

    @property
    def transition_id(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()


class ConventionalEdgeObserverGrid2D(MultiErasureAuthorityGrid2D):
    """W8.5 grid plus a side-effect-free explicit transition-event index."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.transition_records: list[TransitionRecord] = []
        self._transition_ids: set[str] = set()

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
            if transition_id in self._transition_ids:
                raise RuntimeError("duplicate canonical transition identity")
            self._transition_ids.add(transition_id)
            self.transition_records.append(record)

    def transition_metadata_bytes(self) -> int:
        return sum(len(record.canonical_bytes()) for record in self.transition_records)

    def replay(self, initial: str) -> str:
        return replay_transition_records(initial, self.transition_records)


def replay_transition_records(
    initial: str, records: Sequence[TransitionRecord]
) -> str:
    """Replay ordered completed transition facts without consulting MORPHOS runtime."""

    state = list(initial)
    previous_tick = 0
    for record in records:
        if record.logical_tick < previous_tick:
            raise ValueError("transition records are not in logical-time order")
        previous_tick = record.logical_tick
        if not 0 <= record.site < len(state):
            raise ValueError("transition site outside initial state")
        if state[record.site] != record.from_phase:
            raise ValueError("transition history does not compose from prior state")
        state[record.site] = record.to_phase
    return "".join(state)
