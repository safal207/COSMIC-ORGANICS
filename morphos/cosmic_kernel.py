"""COSMIC-KERNEL-05 integrated sparse execution + committed causal proof observer.

The proof collector is strictly observational. The wrapped scheduler owns lattice
state and transitions; proof generation happens only after a completed step and
cannot change states, transition authority, or future dirty-frontier scheduling.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Sequence, Type

from morphos.dag_parent_commit import (
    DagParentCommitProof,
    build_dag_nodes,
    dag_parent_commit_metrics,
    verify_dag_parent_commit,
)
from morphos.grid2d import Grid2DConfig
from morphos.proof_controls_v02 import (
    CommittedPhaseFact,
    TransitionClaim,
    VerificationContext,
    _merkle_leaves,
    _neighbors,
    _parent,
)
from morphos.sparse_scheduler import (
    DirtyNodeGrid2D,
    InstrumentedDenseGrid2D,
    SchedulerCounters,
)

SchedulerType = Type[InstrumentedDenseGrid2D] | Type[DirtyNodeGrid2D]


@dataclass(frozen=True)
class TransitionOccurrence:
    logical_tick: int
    site: int
    from_phase: str
    to_phase: str

    @property
    def canonical_identity(self) -> str:
        payload = (
            f"{self.logical_tick}|{self.site}|{self.from_phase}|{self.to_phase}"
        ).encode("ascii")
        return "sha256:" + hashlib.sha256(payload).hexdigest()


def _batch_committed_facts(
    state: str, tick: int, sites: Sequence[int]
) -> tuple[str, dict[int, CommittedPhaseFact]]:
    """Build one Merkle tree and extract frozen-format paths for many sites."""
    levels = [_merkle_leaves(state)]
    while len(levels[-1]) > 1:
        level = levels[-1]
        levels.append(
            [_parent(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        )
    root = "sha256:" + levels[-1][0].hex()
    facts: dict[int, CommittedPhaseFact] = {}
    for site in sorted(set(sites)):
        if not 0 <= site < len(state):
            raise IndexError("site outside state")
        index = site
        path: list[str] = []
        for level in levels[:-1]:
            path.append(level[index ^ 1].hex())
            index //= 2
        facts[site] = CommittedPhaseFact(
            tick=tick,
            site=site,
            phase=state[site],
            auth_path=tuple(path),
        )
    return root, facts


class CommittedProofKernel:
    """Wrap a frozen scheduler with a deterministic sampled proof observer."""

    def __init__(
        self,
        initial: str,
        *,
        config: Grid2DConfig,
        scheduler_cls: SchedulerType,
        proof_density: float,
        proof_seed: int,
    ) -> None:
        if not 0.0 <= proof_density <= 1.0:
            raise ValueError("proof_density must be in [0, 1]")
        if scheduler_cls not in (InstrumentedDenseGrid2D, DirtyNodeGrid2D):
            raise ValueError("unsupported frozen scheduler")
        self.model = scheduler_cls(initial, config=config)
        self.config = config
        self.proof_density = float(proof_density)
        self.proof_seed = int(proof_seed)
        self.initial_state = initial

        self._claims: list[TransitionClaim] = []
        self._phase_facts: dict[tuple[int, int], CommittedPhaseFact] = {}
        self._state_roots: dict[int, str] = {}
        self._queries: list[tuple[int, int]] = []
        self._stimulus_facts: list[tuple[int, int, float]] = []
        self._transition_trace: list[TransitionOccurrence] = []

    @property
    def states(self):
        return self.model.states

    @property
    def transitions(self) -> int:
        return self.model.transitions

    @property
    def tick(self) -> int:
        return self.model.tick

    def state_string(self) -> str:
        return self.model.state_string()

    def scheduler_counters(self) -> SchedulerCounters:
        return self.model.scheduler_counters()

    @staticmethod
    def _stimuli(stimulus: float | Sequence[float], cells: int) -> list[float]:
        if isinstance(stimulus, (int, float)):
            return [float(stimulus)] * cells
        values = [float(value) for value in stimulus]
        if len(values) != cells:
            raise ValueError("stimulus sequence length must equal cell count")
        return values

    def _selected(self, occurrence: TransitionOccurrence) -> bool:
        if self.proof_density <= 0.0:
            return False
        if self.proof_density >= 1.0:
            return True
        material = (
            f"{occurrence.canonical_identity}|{self.proof_density:.12f}|"
            f"{self.proof_seed}"
        ).encode("ascii")
        value = int.from_bytes(hashlib.sha256(material).digest(), "big")
        return value < int(self.proof_density * (1 << 256))

    def step(self, stimulus: float | Sequence[float] = 0.0) -> None:
        before = self.model.state_string()
        pre_tick = self.model.tick
        transitions_before = self.model.transitions
        stimuli = self._stimuli(stimulus, len(before))

        self.model.step(stimuli)

        after = self.model.state_string()
        logical_tick = self.model.tick
        changed = [
            site for site, (left, right) in enumerate(zip(before, after)) if left != right
        ]
        if len(changed) != self.model.transitions - transitions_before:
            raise RuntimeError("proof observer saw transition/state-delta divergence")

        selected: list[tuple[int, TransitionOccurrence]] = []
        for site in changed:
            occurrence = TransitionOccurrence(
                logical_tick=logical_tick,
                site=site,
                from_phase=before[site],
                to_phase=after[site],
            )
            self._transition_trace.append(occurrence)
            if self._selected(occurrence):
                selected.append((site, occurrence))

        if not selected:
            return

        fact_sites: set[int] = set()
        for site, _ in selected:
            fact_sites.add(site)
            fact_sites.update(_neighbors(site, self.config))
        root, facts = _batch_committed_facts(before, pre_tick, tuple(fact_sites))
        self._state_roots[pre_tick] = root

        for site, occurrence in selected:
            claim = TransitionClaim(logical_tick, site, occurrence.to_phase)
            self._claims.append(claim)
            self._queries.append((logical_tick, site))
            self._stimulus_facts.append((logical_tick, site, stimuli[site]))
            for fact_site in (site, *_neighbors(site, self.config)):
                key = (pre_tick, fact_site)
                fact = facts[fact_site]
                previous = self._phase_facts.get(key)
                if previous is not None and previous != fact:
                    raise RuntimeError("committed phase fact instability")
                self._phase_facts[key] = fact

    def proof(self) -> DagParentCommitProof:
        facts = tuple(self._phase_facts[key] for key in sorted(self._phase_facts))
        claims = tuple(self._claims)
        return DagParentCommitProof(
            phase_facts=facts,
            stimulus_facts=tuple(self._stimulus_facts),
            nodes=build_dag_nodes(claims, self.config),
        )

    def verification_context(self) -> VerificationContext:
        return VerificationContext(
            expected_queries=tuple(self._queries),
            state_roots=tuple(sorted(self._state_roots.items())),
            expected_stimuli=tuple(self._stimulus_facts),
        )

    def verify_proof(self) -> bool:
        return verify_dag_parent_commit(
            self.proof(), self.config, self.verification_context()
        )

    def proof_metrics(self) -> dict:
        metrics = dag_parent_commit_metrics(self.proof(), self.config)
        metrics["audited_transitions"] = len(self._claims)
        return metrics

    @property
    def total_completed_transitions(self) -> int:
        return len(self._transition_trace)

    def replay(self) -> str:
        state = list(self.initial_state)
        previous_tick = 0
        for record in self._transition_trace:
            if record.logical_tick < previous_tick:
                raise RuntimeError("transition trace is not monotone in logical time")
            previous_tick = record.logical_tick
            if state[record.site] != record.from_phase:
                raise RuntimeError("transition trace does not compose")
            state[record.site] = record.to_phase
        return "".join(state)
