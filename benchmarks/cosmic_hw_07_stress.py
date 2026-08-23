from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from morphos.grid2d import Grid2D, Grid2DConfig

CELLS = 64
TICKS = 12
SEQUENCES = 64

CLASSES = (
    "all_64_transition_tick",
    "adjacent_collision_cluster",
    "alternating_high_low_transition_bursts",
    "back_to_back_transition_heavy_ticks",
    "zero_transition_ticks",
)

READY_PATTERNS = (
    "always_ready",
    "three_ready_one_blocked",
    "alternating_ready_blocked",
    "eight_cycle_block_bursts",
)


def receipt_ready(pattern: str, cycle: int) -> bool:
    if pattern == "always_ready":
        return True
    if pattern == "three_ready_one_blocked":
        return cycle % 4 != 3
    if pattern == "alternating_ready_blocked":
        return cycle % 2 == 0
    if pattern == "eight_cycle_block_bursts":
        return cycle % 16 >= 8
    raise ValueError(f"unknown ready pattern: {pattern}")


def _zero() -> list[int]:
    return [0] * CELLS


def _pulse(sites, amplitude: int) -> tuple[int, ...]:
    row = _zero()
    for site in sites:
        row[site] = amplitude
    return tuple(row)


def _all(amplitude: int) -> tuple[int, ...]:
    return tuple([amplitude] * CELLS)


def _cluster(index: int) -> tuple[int, ...]:
    # Deterministic 2x2 cluster kept away from the outer boundary.
    base_row = 1 + (index * 2) % 5
    base_col = 1 + (index * 3) % 5
    return tuple(
        sorted(
            {
                base_row * 8 + base_col,
                base_row * 8 + base_col + 1,
                (base_row + 1) * 8 + base_col,
                (base_row + 1) * 8 + base_col + 1,
            }
        )
    )


def _half_sites(index: int) -> tuple[int, ...]:
    parity = index & 1
    return tuple(site for site in range(CELLS) if ((site // 8) + (site % 8)) % 2 == parity)


@dataclass(frozen=True)
class ReceiptStressSequence:
    vector_id: str
    stress_class: str
    ready_pattern: str
    initial_state: str
    stimuli_s100: tuple[tuple[int, ...], ...]

    def to_jsonable(self) -> dict:
        return {
            "vector_id": self.vector_id,
            "stress_class": self.stress_class,
            "ready_pattern": self.ready_pattern,
            "initial_state": self.initial_state,
            "stimuli_s100": [list(row) for row in self.stimuli_s100],
        }


def _build_ticks(stress_class: str, index: int) -> tuple[tuple[int, ...], ...]:
    ticks = [tuple(_zero()) for _ in range(TICKS)]

    if stress_class == "all_64_transition_tick":
        ticks[0] = _all(80)
        ticks[1] = _all(80)
        ticks[4] = _all(-80)
        ticks[5] = _all(-80)

    elif stress_class == "adjacent_collision_cluster":
        sites = _cluster(index)
        ticks[0] = _pulse(sites, 80)
        ticks[1] = _pulse(sites, 80)
        ticks[3] = _pulse(sites, 80)
        ticks[5] = _pulse(sites, -80)
        ticks[6] = _pulse(sites, -80)

    elif stress_class == "alternating_high_low_transition_bursts":
        for tick in (0, 1, 4, 5, 8, 9):
            ticks[tick] = _all(80)
        for tick in (2, 3, 6, 7, 10, 11):
            ticks[tick] = _all(-80)

    elif stress_class == "back_to_back_transition_heavy_ticks":
        first = _half_sites(index)
        second = tuple(site for site in range(CELLS) if site not in set(first))
        ticks[0] = _pulse(first, 80)
        ticks[1] = _pulse(first, 80)
        ticks[2] = _pulse(second, 80)
        ticks[3] = _pulse(second, 80)
        ticks[4] = _pulse(first, -80)
        ticks[5] = _pulse(first, -80)
        ticks[6] = _pulse(second, -80)
        ticks[7] = _pulse(second, -80)

    elif stress_class == "zero_transition_ticks":
        # Uniform +/-0.20 remains below both A/C thresholds from the frozen
        # quiescent state and therefore exercises empty-batch reservation release.
        ticks[0] = _all(20)
        ticks[1] = _all(20)
        ticks[4] = _all(-20)
        ticks[5] = _all(-20)
        ticks[8] = _all(20)

    else:
        raise ValueError(stress_class)

    return tuple(ticks)


def build_stress_sequences() -> tuple[ReceiptStressSequence, ...]:
    result = []
    for index in range(SEQUENCES):
        stress_class = CLASSES[index % len(CLASSES)]
        ready_pattern = READY_PATTERNS[index % len(READY_PATTERNS)]
        result.append(
            ReceiptStressSequence(
                vector_id=f"receipt-stress-{index:02d}",
                stress_class=stress_class,
                ready_pattern=ready_pattern,
                initial_state="A" * CELLS,
                stimuli_s100=_build_ticks(stress_class, index),
            )
        )
    return tuple(result)


def transition_oracle(sequence: ReceiptStressSequence) -> tuple[dict, ...]:
    config = Grid2DConfig(width=8, height=8, memory_decay=0.0)
    model = Grid2D(sequence.initial_state, config=config)
    rows = []
    for logical_tick, stimulus_s100 in enumerate(sequence.stimuli_s100, start=1):
        before = model.state_string()
        model.step([value / 100.0 for value in stimulus_s100])
        after = model.state_string()
        transitions = tuple(
            {
                "logical_tick": logical_tick,
                "site_id": site,
                "phase_before": left,
                "phase_after": right,
                "stimulus_s100": stimulus_s100[site],
                "ordinal_in_batch": ordinal,
            }
            for ordinal, (site, (left, right)) in enumerate(
                (item for item in enumerate(zip(before, after)) if item[1][0] != item[1][1])
            )
        )
        rows.append(
            {
                "logical_tick": logical_tick,
                "transition_count": len(transitions),
                "transitions": transitions,
            }
        )
    return tuple(rows)


def corpus_fingerprint() -> str:
    payload = [sequence.to_jsonable() for sequence in build_stress_sequences()]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def validate_stress_corpus() -> dict:
    sequences = build_stress_sequences()
    assert len(sequences) == SEQUENCES
    assert {sequence.stress_class for sequence in sequences} == set(CLASSES)
    assert {sequence.ready_pattern for sequence in sequences} == set(READY_PATTERNS)

    directions = set()
    maximum_batch = 0
    zero_transition_ticks = 0
    consecutive_heavy_pairs = 0
    total_transitions = 0

    for sequence in sequences:
        oracle = transition_oracle(sequence)
        counts = [row["transition_count"] for row in oracle]
        maximum_batch = max(maximum_batch, *counts)
        zero_transition_ticks += sum(count == 0 for count in counts)
        consecutive_heavy_pairs += sum(
            left >= 32 and right >= 32 for left, right in zip(counts, counts[1:])
        )
        total_transitions += sum(counts)
        for row in oracle:
            for transition in row["transitions"]:
                directions.add((transition["phase_before"], transition["phase_after"]))

    assert maximum_batch == 64
    assert zero_transition_ticks > 0
    assert consecutive_heavy_pairs > 0
    assert directions == {("A", "M"), ("M", "C"), ("C", "M"), ("M", "A")}

    return {
        "sequences": len(sequences),
        "ticks": len(sequences) * TICKS,
        "maximum_batch": maximum_batch,
        "zero_transition_ticks": zero_transition_ticks,
        "consecutive_heavy_pairs": consecutive_heavy_pairs,
        "total_transitions": total_transitions,
        "directions": sorted([list(item) for item in directions]),
        "fingerprint": corpus_fingerprint(),
    }


if __name__ == "__main__":
    print(json.dumps(validate_stress_corpus(), sort_keys=True))
