"""BARDO-PROOF-03 conventional proof controls.

Only SNAPSHOT_LOCAL, LOCAL_WITNESS, and CAUSAL_DAG are implemented here.
BARDO_PROOF_EDGE is intentionally absent until the control boundary is frozen.

Verifiers operate exclusively on disclosed proof data plus the frozen Grid2D
configuration. They do not consult a live MORPHOS model or future state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable, Mapping, Sequence

from morphos.grid2d import Grid2DConfig, _PHASES, _VALUE


def _canonical_bytes(value) -> bytes:
    if hasattr(value, "to_jsonable"):
        value = value.to_jsonable()
    elif hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _neighbors(site: int, config: Grid2DConfig) -> tuple[int, ...]:
    row, col = divmod(site, config.width)
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if config.neighborhood == "moore":
        offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    result = []
    for dr, dc in offsets:
        rr, cc = row + dr, col + dc
        if 0 <= rr < config.height and 0 <= cc < config.width:
            result.append(rr * config.width + cc)
    return tuple(result)


def _is_anchor(site: int, config: Grid2DConfig) -> bool:
    row, col = divmod(site, config.width)
    if config.mask == "checkerboard":
        return (row + col) % 2 == 0
    if config.mask == "row_stripes":
        return row % 2 == 0
    if config.mask == "column_stripes":
        return col % 2 == 0
    return (row < config.height // 2) == (col < config.width // 2)


def evaluate_local_transition(
    *,
    site: int,
    phase_before: str,
    neighbor_phases: Sequence[str],
    stimulus: float,
    config: Grid2DConfig,
) -> str:
    """Evaluate one frozen Grid2D local update from disclosed pre-tick facts."""
    if config.memory_decay != 0.0:
        raise ValueError("BARDO-PROOF-03 requires memory_decay == 0")
    if phase_before not in _PHASES:
        raise ValueError("unsupported phase")
    expected_neighbors = _neighbors(site, config)
    if len(neighbor_phases) != len(expected_neighbors):
        raise ValueError("wrong neighbor fact count")
    if any(phase not in _PHASES for phase in neighbor_phases):
        raise ValueError("unsupported neighbor phase")

    anchor = _is_anchor(site, config)
    threshold = config.anchor_threshold if anchor else config.adaptive_threshold
    coupling = config.anchor_coupling if anchor else config.adaptive_coupling
    neighbor_mean = sum(_VALUE[phase] for phase in neighbor_phases) / len(
        neighbor_phases
    )
    drive = float(stimulus) + coupling * (neighbor_mean - _VALUE[phase_before])
    transition_threshold = (
        config.mixed_relax_threshold if phase_before == "M" else threshold
    )
    direction = 0
    if drive >= transition_threshold:
        direction = 1
    elif drive <= -transition_threshold:
        direction = -1
    phase_index = _PHASES.index(phase_before)
    next_index = max(0, min(len(_PHASES) - 1, phase_index + direction))
    return _PHASES[next_index]


@dataclass(frozen=True)
class TransitionClaim:
    logical_tick: int
    site: int
    phase_after: str

    def __post_init__(self) -> None:
        if self.logical_tick <= 0:
            raise ValueError("logical_tick must be positive")
        if self.site < 0:
            raise ValueError("site must be non-negative")
        if self.phase_after not in _PHASES:
            raise ValueError("unsupported phase_after")

    @property
    def claim_id(self) -> str:
        return "sha256:" + hashlib.sha256(_canonical_bytes(self)).hexdigest()


@dataclass(frozen=True)
class SnapshotItem:
    claim: TransitionClaim
    pre_tick_state: str
    local_stimulus: float


@dataclass(frozen=True)
class SnapshotLocalProof:
    items: tuple[SnapshotItem, ...]

    def to_jsonable(self) -> dict:
        return {"items": [asdict(item) for item in self.items]}

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self)


@dataclass(frozen=True)
class LocalWitness:
    claim: TransitionClaim
    phase_before: str
    neighbors: tuple[tuple[int, str], ...]
    local_stimulus: float


@dataclass(frozen=True)
class LocalWitnessProof:
    witnesses: tuple[LocalWitness, ...]

    def to_jsonable(self) -> dict:
        return {
            "witnesses": [
                {
                    "claim": asdict(witness.claim),
                    "phase_before": witness.phase_before,
                    "neighbors": [list(item) for item in witness.neighbors],
                    "local_stimulus": witness.local_stimulus,
                }
                for witness in self.witnesses
            ]
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self)


@dataclass(frozen=True)
class DagClaim:
    claim: TransitionClaim
    parent_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CausalDagProof:
    """Deduplicated fact store plus explicit transition-parent identities."""

    phase_facts: tuple[tuple[int, int, str], ...]
    stimulus_facts: tuple[tuple[int, int, float], ...]
    claims: tuple[DagClaim, ...]

    def to_jsonable(self) -> dict:
        return {
            "phase_facts": [list(item) for item in self.phase_facts],
            "stimulus_facts": [list(item) for item in self.stimulus_facts],
            "claims": [
                {
                    "claim": asdict(item.claim),
                    "parent_ids": list(item.parent_ids),
                }
                for item in self.claims
            ],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self)


def verify_snapshot_local(
    proof: SnapshotLocalProof,
    config: Grid2DConfig,
    expected_queries: Sequence[tuple[int, int]],
) -> bool:
    if len(proof.items) != len(expected_queries):
        return False
    cells = config.width * config.height
    for item, expected in zip(proof.items, expected_queries):
        claim = item.claim
        if (claim.logical_tick, claim.site) != tuple(expected):
            return False
        if len(item.pre_tick_state) != cells:
            return False
        if any(phase not in _PHASES for phase in item.pre_tick_state):
            return False
        neighbor_sites = _neighbors(claim.site, config)
        expected_after = evaluate_local_transition(
            site=claim.site,
            phase_before=item.pre_tick_state[claim.site],
            neighbor_phases=[item.pre_tick_state[index] for index in neighbor_sites],
            stimulus=item.local_stimulus,
            config=config,
        )
        if expected_after != claim.phase_after:
            return False
    return True


def verify_local_witness(
    proof: LocalWitnessProof,
    config: Grid2DConfig,
    expected_queries: Sequence[tuple[int, int]],
) -> bool:
    if len(proof.witnesses) != len(expected_queries):
        return False
    for witness, expected in zip(proof.witnesses, expected_queries):
        claim = witness.claim
        if (claim.logical_tick, claim.site) != tuple(expected):
            return False
        required_sites = _neighbors(claim.site, config)
        if tuple(site for site, _ in witness.neighbors) != required_sites:
            return False
        try:
            expected_after = evaluate_local_transition(
                site=claim.site,
                phase_before=witness.phase_before,
                neighbor_phases=[phase for _, phase in witness.neighbors],
                stimulus=witness.local_stimulus,
                config=config,
            )
        except ValueError:
            return False
        if expected_after != claim.phase_after:
            return False
    return True


def _fact_map(
    facts: Iterable[tuple[int, int, object]],
) -> dict[tuple[int, int], object] | None:
    result: dict[tuple[int, int], object] = {}
    for tick, site, value in facts:
        key = (tick, site)
        if key in result and result[key] != value:
            return None
        result[key] = value
    return result


def verify_causal_dag(
    proof: CausalDagProof,
    config: Grid2DConfig,
    expected_queries: Sequence[tuple[int, int]],
) -> bool:
    if len(proof.claims) != len(expected_queries):
        return False
    phase_facts = _fact_map(proof.phase_facts)
    stimulus_facts = _fact_map(proof.stimulus_facts)
    if phase_facts is None or stimulus_facts is None:
        return False

    claims_by_id = {item.claim.claim_id: item for item in proof.claims}
    if len(claims_by_id) != len(proof.claims):
        return False
    claims_by_tick_site = {
        (item.claim.logical_tick, item.claim.site): item for item in proof.claims
    }
    if len(claims_by_tick_site) != len(proof.claims):
        return False

    for item, expected in zip(proof.claims, expected_queries):
        claim = item.claim
        if (claim.logical_tick, claim.site) != tuple(expected):
            return False
        pre_tick = claim.logical_tick - 1
        phase_before = phase_facts.get((pre_tick, claim.site))
        stimulus = stimulus_facts.get((claim.logical_tick, claim.site))
        if phase_before not in _PHASES or stimulus is None:
            return False
        neighbor_sites = _neighbors(claim.site, config)
        neighbor_phases = [phase_facts.get((pre_tick, site)) for site in neighbor_sites]
        if any(phase not in _PHASES for phase in neighbor_phases):
            return False

        required_parent_ids = []
        for site in (claim.site, *neighbor_sites):
            parent = claims_by_tick_site.get((pre_tick, site))
            if parent is not None:
                # Parent claim must compose with the disclosed pre-tick fact.
                if parent.claim.phase_after != phase_facts[(pre_tick, site)]:
                    return False
                required_parent_ids.append(parent.claim.claim_id)
        if tuple(sorted(item.parent_ids)) != tuple(sorted(required_parent_ids)):
            return False
        if any(parent_id not in claims_by_id for parent_id in item.parent_ids):
            return False

        try:
            expected_after = evaluate_local_transition(
                site=claim.site,
                phase_before=phase_before,
                neighbor_phases=neighbor_phases,
                stimulus=float(stimulus),
                config=config,
            )
        except ValueError:
            return False
        if expected_after != claim.phase_after:
            return False
    return True


def proof_metrics(proof, config: Grid2DConfig) -> dict:
    """Return deterministic representation/work counters for a control proof."""
    if isinstance(proof, SnapshotLocalProof):
        phase_keys = set()
        stimulus_keys = set()
        for item in proof.items:
            pre_tick = item.claim.logical_tick - 1
            for site in range(len(item.pre_tick_state)):
                phase_keys.add((pre_tick, site))
            stimulus_keys.add((item.claim.logical_tick, item.claim.site))
        return {
            "canonical_proof_payload_bytes": len(proof.canonical_bytes()),
            "unique_phase_facts_disclosed": len(phase_keys),
            "unique_stimulus_facts_disclosed": len(stimulus_keys),
            "parent_references_disclosed": 0,
            "local_transition_evaluations": len(proof.items),
            "hash_evaluations": 0,
            "proof_objects_traversed": len(proof.items),
        }
    if isinstance(proof, LocalWitnessProof):
        phase_keys = set()
        stimulus_keys = set()
        for witness in proof.witnesses:
            pre_tick = witness.claim.logical_tick - 1
            phase_keys.add((pre_tick, witness.claim.site))
            for site, _ in witness.neighbors:
                phase_keys.add((pre_tick, site))
            stimulus_keys.add((witness.claim.logical_tick, witness.claim.site))
        return {
            "canonical_proof_payload_bytes": len(proof.canonical_bytes()),
            "unique_phase_facts_disclosed": len(phase_keys),
            "unique_stimulus_facts_disclosed": len(stimulus_keys),
            "parent_references_disclosed": 0,
            "local_transition_evaluations": len(proof.witnesses),
            "hash_evaluations": 0,
            "proof_objects_traversed": len(proof.witnesses),
        }
    if isinstance(proof, CausalDagProof):
        parent_refs = sum(len(item.parent_ids) for item in proof.claims)
        # claim_id is SHA-256 over each selected transition claim and is required
        # for parent identity/composition checks.
        return {
            "canonical_proof_payload_bytes": len(proof.canonical_bytes()),
            "unique_phase_facts_disclosed": len(proof.phase_facts),
            "unique_stimulus_facts_disclosed": len(proof.stimulus_facts),
            "parent_references_disclosed": parent_refs,
            "local_transition_evaluations": len(proof.claims),
            "hash_evaluations": len(proof.claims) + parent_refs,
            "proof_objects_traversed": len(proof.claims) + len(proof.phase_facts) + len(proof.stimulus_facts),
        }
    raise TypeError("unsupported proof type")
