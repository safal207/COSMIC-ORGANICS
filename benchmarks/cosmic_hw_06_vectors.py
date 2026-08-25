from __future__ import annotations

from dataclasses import dataclass
import random

WIDTH = 8
HEIGHT = 8
CELLS = WIDTH * HEIGHT
DENSITIES = (0.01, 0.05, 0.20, 1.00)
SEED_FAMILIES = (202608237001, 202608237002)
SEQUENCES_PER_DENSITY = 64
TICKS_PER_SEQUENCE = 12
# Stimuli are integer hundredths. These values deliberately avoid threshold-edge
# equality so the fixed-point RTL can be checked against the frozen Python model.
AMPLITUDES_S100 = (80, 60, 40, -40, -60, -80)


@dataclass(frozen=True)
class HardwareVectorSequence:
    vector_id: str
    density: float
    family: int
    initial_state: str
    stimuli_s100: tuple[tuple[int, ...], ...]


def active_count(density: float) -> int:
    return max(1, min(CELLS, round(CELLS * density)))


def _mask_for(rng: random.Random, count: int) -> tuple[int, ...]:
    if count == CELLS:
        return tuple(range(CELLS))
    return tuple(sorted(rng.sample(range(CELLS), count)))


def _pulse(mask: tuple[int, ...], amplitude: int) -> tuple[int, ...]:
    row = [0] * CELLS
    for site in mask:
        row[site] = amplitude
    return tuple(row)


def build_sequences() -> tuple[HardwareVectorSequence, ...]:
    result: list[HardwareVectorSequence] = []
    per_family = SEQUENCES_PER_DENSITY // len(SEED_FAMILIES)
    for density_index, density in enumerate(DENSITIES):
        count = active_count(density)
        for family in SEED_FAMILIES:
            for local_index in range(per_family):
                seed = family + density_index * 100_000 + local_index
                rng = random.Random(seed)
                mask_a = _mask_for(rng, count)
                mask_b = _mask_for(rng, count)
                positive = (80, 60, 40)[local_index % 3]
                negative = (-80, -60, -40)[(local_index // 3) % 3]

                # Three explicit pulses separated by relaxation/change ticks.
                # Reusing mask_a with opposite sign ensures C->M/M->A routes are
                # reachable after prior positive drive; mask_b exercises frontier
                # movement and collisions independently.
                ticks = [tuple([0] * CELLS) for _ in range(TICKS_PER_SEQUENCE)]
                ticks[0] = _pulse(mask_a, positive)
                ticks[1] = _pulse(mask_a, positive)
                ticks[2] = _pulse(mask_a, positive)
                ticks[4] = _pulse(mask_b, positive)
                ticks[5] = _pulse(mask_b, positive)
                ticks[8] = _pulse(mask_a, negative)
                ticks[9] = _pulse(mask_a, negative)
                ticks[10] = _pulse(mask_a, negative)

                result.append(
                    HardwareVectorSequence(
                        vector_id=(
                            f"d{int(density * 100):03d}-f{family}-v{local_index:02d}"
                        ),
                        density=density,
                        family=family,
                        initial_state="A" * CELLS,
                        stimuli_s100=tuple(ticks),
                    )
                )
    assert len(result) == len(DENSITIES) * SEQUENCES_PER_DENSITY == 256
    return tuple(result)


def validate_vectors() -> None:
    vectors = build_sequences()
    assert len(vectors) == 256
    assert {v.density for v in vectors} == set(DENSITIES)
    for density in DENSITIES:
        rows = [v for v in vectors if v.density == density]
        assert len(rows) == 64
    for vector in vectors:
        assert len(vector.initial_state) == CELLS
        assert len(vector.stimuli_s100) == TICKS_PER_SEQUENCE
        for tick in vector.stimuli_s100:
            assert len(tick) == CELLS
            assert all(-128 <= value <= 127 for value in tick)
            assert all(value == 0 or value in AMPLITUDES_S100 for value in tick)


if __name__ == "__main__":
    validate_vectors()
    print("COSMIC_HW_06_VECTORS_PASS sequences=256 ticks_per_sequence=12")
