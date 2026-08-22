"""Commitment-bound conventional controls for BARDO-PROOF-03/v0.2.

A public SHA-256 Merkle root binds each disclosed pre-tick state fact. External
stimulus is treated as public frozen query input. Verifiers use no live model,
undisclosed state, target truth, or future state.

BARDO_PROOF_EDGE remains intentionally absent from this controls-only module.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Sequence

from morphos.grid2d import Grid2DConfig, _PHASES, _VALUE


def _json_bytes(value) -> bytes:
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


def _sha(payload: bytes) -> bytes:
    return hashlib.sha256(payload).digest()


def _leaf(site: int, phase: str) -> bytes:
    return _sha(f"state-leaf:{site}:{phase}".encode("ascii"))


def _empty_leaf(index: int) -> bytes:
    return _sha(f"state-empty:{index}".encode("ascii"))


def _parent(left: bytes, right: bytes) -> bytes:
    return _sha(b"state-node:" + left + right)


def _padded_leaf_count(count: int) -> int:
    if count <= 0:
        raise ValueError("leaf count must be positive")
    value = 1
    while value < count:
        value <<= 1
    return value


def _merkle_leaves(state: str) -> list[bytes]:
    if not state or any(phase not in _PHASES for phase in state):
        raise ValueError("state must be non-empty A/M/C")
    padded = _padded_leaf_count(len(state))
    leaves = [_leaf(site, phase) for site, phase in enumerate(state)]
    leaves.extend(_empty_leaf(site) for site in range(len(state), padded))
    return leaves


def state_root(state: str) -> str:
    level = _merkle_leaves(state)
    while len(level) > 1:
        level = [_parent(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return "sha256:" + level[0].hex()


def state_auth_path(state: str, site: int) -> tuple[str, ...]:
    if not 0 <= site < len(state):
        raise IndexError("site outside state")
    level = _merkle_leaves(state)
    index = site
    path: list[str] = []
    while len(level) > 1:
        sibling = index ^ 1
        path.append(level[sibling].hex())
        level = [_parent(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        index //= 2
    return tuple(path)


def verify_state_fact(
    *, site: int, phase: str, auth_path: Sequence[str], expected_root: str
) -> bool:
    if site < 0 or phase not in _PHASES or not expected_root.startswith("sha256:"):
        return False
    try:
        current = _leaf(site, phase)
        index = site
        for sibling_hex in auth_path:
            sibling = bytes.fromhex(sibling_hex)
            if len(sibling) != 32:
                return False
            if index % 2 == 0:
                current = _parent(current, sibling)
            else:
                current = _parent(sibling, current)
            index //= 2
    except ValueError:
        return False
    return "sha256:" + current.hex() == expected_root


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
    if config.memory_decay != 0.0:
        raise ValueError("BARDO-PROOF-03/v0.2 requires memory_decay == 0")
    required = _neighbors(site, config)
    if phase_before not in _PHASES or len(neighbor_phases) != len(required):
        raise ValueError("invalid local state facts")
    if any(phase not in _PHASES for phase in neighbor_phases):
        raise ValueError("invalid neighbor phase")
    anchor = _is_anchor(site, config)
    threshold = config.anchor_threshold if anchor else config.adaptive_threshold
    coupling = config.anchor_coupling if anchor else config.adaptive_coupling
    neighbor_mean = sum(_VALUE[phase] for phase in neighbor_phases) / len(neighbor_phases)
    drive = float(stimulus) + coupling * (neighbor_mean - _VALUE[phase_before])
    transition_threshold = config.mixed_relax_threshold if phase_before == "M" else threshold
    direction = 1 if drive >= transition_threshold else -1 if drive <= -transition_threshold else 0
    current_index = _PHASES.index(phase_before)
    return _PHASES[max(0, min(len(_PHASES) - 1, current_index + direction))]


@dataclass(frozen=True)
class VerificationContext:
    expected_queries: tuple[tuple[int, int], ...]
    state_roots: tuple[tuple[int, str], ...]
    expected_stimuli: tuple[tuple[int, int, float], ...]

    def state_root_at(self, tick: int) -> str | None:
        return dict(self.state_roots).get(tick)

    def stimulus_at(self, tick: int, site: int) -> float | None:
        return {(t, s): value for t, s, value in self.expected_stimuli}.get((tick, site))


@dataclass(frozen=True)
class TransitionClaim:
    logical_tick: int
    site: int
    phase_after: str

    @property
    def claim_id(self) -> str:
        return "sha256:" + hashlib.sha256(_json_bytes(self)).hexdigest()


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
        return _json_bytes(self)


@dataclass(frozen=True)
class CommittedPhaseFact:
    tick: int
    site: int
    phase: str
    auth_path: tuple[str, ...]


@dataclass(frozen=True)
class LocalWitness:
    claim: TransitionClaim
    phase_before: CommittedPhaseFact
    neighbors: tuple[CommittedPhaseFact, ...]
    local_stimulus: float


@dataclass(frozen=True)
class LocalWitnessProof:
    witnesses: tuple[LocalWitness, ...]

    def to_jsonable(self) -> dict:
        return {
            "witnesses": [
                {
                    "claim": asdict(w.claim),
                    "phase_before": asdict(w.phase_before),
                    "neighbors": [asdict(fact) for fact in w.neighbors],
                    "local_stimulus": w.local_stimulus,
                }
                for w in self.witnesses
            ]
        }

    def canonical_bytes(self) -> bytes:
        return _json_bytes(self)


@dataclass(frozen=True)
class DagClaim:
    claim: TransitionClaim
    parent_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CausalDagProof:
    phase_facts: tuple[CommittedPhaseFact, ...]
    stimulus_facts: tuple[tuple[int, int, float], ...]
    claims: tuple[DagClaim, ...]

    def to_jsonable(self) -> dict:
        return {
            "phase_facts": [asdict(fact) for fact in self.phase_facts],
            "stimulus_facts": [list(item) for item in self.stimulus_facts],
            "claims": [
                {"claim": asdict(item.claim), "parent_ids": list(item.parent_ids)}
                for item in self.claims
            ],
        }

    def canonical_bytes(self) -> bytes:
        return _json_bytes(self)


def committed_fact(state: str, tick: int, site: int) -> CommittedPhaseFact:
    return CommittedPhaseFact(tick, site, state[site], state_auth_path(state, site))


def _context_matches(claim: TransitionClaim, stimulus: float, context: VerificationContext) -> bool:
    return (
        (claim.logical_tick, claim.site) in context.expected_queries
        and context.stimulus_at(claim.logical_tick, claim.site) == float(stimulus)
    )


def verify_snapshot_local(proof: SnapshotLocalProof, config: Grid2DConfig, context: VerificationContext) -> bool:
    if len(proof.items) != len(context.expected_queries):
        return False
    cells = config.width * config.height
    for item, expected in zip(proof.items, context.expected_queries):
        claim = item.claim
        if (claim.logical_tick, claim.site) != expected or not _context_matches(claim, item.local_stimulus, context):
            return False
        if len(item.pre_tick_state) != cells:
            return False
        root = context.state_root_at(claim.logical_tick - 1)
        if root is None:
            return False
        try:
            if state_root(item.pre_tick_state) != root:
                return False
            neighbor_sites = _neighbors(claim.site, config)
            expected_after = evaluate_local_transition(
                site=claim.site,
                phase_before=item.pre_tick_state[claim.site],
                neighbor_phases=[item.pre_tick_state[site] for site in neighbor_sites],
                stimulus=item.local_stimulus,
                config=config,
            )
        except (ValueError, IndexError):
            return False
        if expected_after != claim.phase_after:
            return False
    return True


def _verify_local_fact(fact: CommittedPhaseFact, expected_tick: int, expected_site: int, context: VerificationContext) -> bool:
    if fact.tick != expected_tick or fact.site != expected_site:
        return False
    root = context.state_root_at(expected_tick)
    return root is not None and verify_state_fact(
        site=fact.site,
        phase=fact.phase,
        auth_path=fact.auth_path,
        expected_root=root,
    )


def verify_local_witness(proof: LocalWitnessProof, config: Grid2DConfig, context: VerificationContext) -> bool:
    if len(proof.witnesses) != len(context.expected_queries):
        return False
    for witness, expected in zip(proof.witnesses, context.expected_queries):
        claim = witness.claim
        if (claim.logical_tick, claim.site) != expected or not _context_matches(claim, witness.local_stimulus, context):
            return False
        pre_tick = claim.logical_tick - 1
        if not _verify_local_fact(witness.phase_before, pre_tick, claim.site, context):
            return False
        required_sites = _neighbors(claim.site, config)
        if tuple(fact.site for fact in witness.neighbors) != required_sites:
            return False
        for fact, site in zip(witness.neighbors, required_sites):
            if not _verify_local_fact(fact, pre_tick, site, context):
                return False
        try:
            expected_after = evaluate_local_transition(
                site=claim.site,
                phase_before=witness.phase_before.phase,
                neighbor_phases=[fact.phase for fact in witness.neighbors],
                stimulus=witness.local_stimulus,
                config=config,
            )
        except ValueError:
            return False
        if expected_after != claim.phase_after:
            return False
    return True


def verify_causal_dag(proof: CausalDagProof, config: Grid2DConfig, context: VerificationContext) -> bool:
    if len(proof.claims) != len(context.expected_queries):
        return False
    fact_map: dict[tuple[int, int], CommittedPhaseFact] = {}
    for fact in proof.phase_facts:
        key = (fact.tick, fact.site)
        if key in fact_map and fact_map[key] != fact:
            return False
        if not _verify_local_fact(fact, fact.tick, fact.site, context):
            return False
        fact_map[key] = fact
    stimulus_map: dict[tuple[int, int], float] = {}
    for tick, site, value in proof.stimulus_facts:
        key = (tick, site)
        if key in stimulus_map and stimulus_map[key] != value:
            return False
        expected = context.stimulus_at(tick, site)
        if expected is None or expected != float(value):
            return False
        stimulus_map[key] = float(value)

    claims_by_id = {item.claim.claim_id: item for item in proof.claims}
    claims_by_tick_site = {(item.claim.logical_tick, item.claim.site): item for item in proof.claims}
    if len(claims_by_id) != len(proof.claims) or len(claims_by_tick_site) != len(proof.claims):
        return False

    for item, expected_query in zip(proof.claims, context.expected_queries):
        claim = item.claim
        if (claim.logical_tick, claim.site) != expected_query:
            return False
        pre_tick = claim.logical_tick - 1
        own = fact_map.get((pre_tick, claim.site))
        stimulus = stimulus_map.get((claim.logical_tick, claim.site))
        if own is None or stimulus is None:
            return False
        neighbor_sites = _neighbors(claim.site, config)
        neighbors = [fact_map.get((pre_tick, site)) for site in neighbor_sites]
        if any(fact is None for fact in neighbors):
            return False

        required_parent_ids = []
        for site in (claim.site, *neighbor_sites):
            parent = claims_by_tick_site.get((pre_tick, site))
            if parent is not None:
                disclosed = fact_map[(pre_tick, site)]
                if parent.claim.phase_after != disclosed.phase:
                    return False
                required_parent_ids.append(parent.claim.claim_id)
        if tuple(sorted(item.parent_ids)) != tuple(sorted(required_parent_ids)):
            return False
        if any(parent_id not in claims_by_id for parent_id in item.parent_ids):
            return False

        try:
            expected_after = evaluate_local_transition(
                site=claim.site,
                phase_before=own.phase,
                neighbor_phases=[fact.phase for fact in neighbors if fact is not None],
                stimulus=stimulus,
                config=config,
            )
        except ValueError:
            return False
        if expected_after != claim.phase_after:
            return False
    return True


def _tree_hash_count(cells: int) -> int:
    padded = _padded_leaf_count(cells)
    return padded + (padded - 1)


def proof_metrics(proof, config: Grid2DConfig) -> dict:
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
            "merkle_sibling_hashes_disclosed": 0,
            "unique_stimulus_facts_disclosed": len(stimulus_keys),
            "parent_references_disclosed": 0,
            "local_transition_evaluations": len(proof.items),
            "hash_evaluations": len(proof.items) * _tree_hash_count(config.width * config.height),
            "proof_objects_traversed": len(proof.items),
        }
    if isinstance(proof, LocalWitnessProof):
        phase_keys = set()
        stimulus_keys = set()
        paths = 0
        for witness in proof.witnesses:
            phase_keys.add((witness.phase_before.tick, witness.phase_before.site))
            paths += len(witness.phase_before.auth_path)
            for fact in witness.neighbors:
                phase_keys.add((fact.tick, fact.site))
                paths += len(fact.auth_path)
            stimulus_keys.add((witness.claim.logical_tick, witness.claim.site))
        fact_occurrences = sum(1 + len(w.neighbors) for w in proof.witnesses)
        return {
            "canonical_proof_payload_bytes": len(proof.canonical_bytes()),
            "unique_phase_facts_disclosed": len(phase_keys),
            "merkle_sibling_hashes_disclosed": paths,
            "unique_stimulus_facts_disclosed": len(stimulus_keys),
            "parent_references_disclosed": 0,
            "local_transition_evaluations": len(proof.witnesses),
            "hash_evaluations": fact_occurrences + paths,
            "proof_objects_traversed": len(proof.witnesses) + fact_occurrences,
        }
    if isinstance(proof, CausalDagProof):
        paths = sum(len(fact.auth_path) for fact in proof.phase_facts)
        parent_refs = sum(len(item.parent_ids) for item in proof.claims)
        return {
            "canonical_proof_payload_bytes": len(proof.canonical_bytes()),
            "unique_phase_facts_disclosed": len(proof.phase_facts),
            "merkle_sibling_hashes_disclosed": paths,
            "unique_stimulus_facts_disclosed": len(proof.stimulus_facts),
            "parent_references_disclosed": parent_refs,
            "local_transition_evaluations": len(proof.claims),
            "hash_evaluations": len(proof.phase_facts) + paths + len(proof.claims) + parent_refs,
            "proof_objects_traversed": len(proof.phase_facts) + len(proof.stimulus_facts) + len(proof.claims),
        }
    raise TypeError("unsupported proof type")
