from benchmarks.cosmic_hw_06_vectors import CELLS, build_sequences, validate_vectors
from morphos.grid2d import Grid2D, Grid2DConfig, _PHASES


def _neighbors(site: int) -> tuple[int, ...]:
    row, col = divmod(site, 8)
    result = []
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        rr, cc = row + dr, col + dc
        if 0 <= rr < 8 and 0 <= cc < 8:
            result.append(rr * 8 + cc)
    return tuple(result)


def _anchor(site: int) -> bool:
    row, col = divmod(site, 8)
    return (row + col) % 2 == 0


def _exact_step(state: str, stimulus_s100: tuple[int, ...]) -> str:
    value2 = {"A": 0, "M": 1, "C": 2}
    next_state = list(state)
    for site, phase in enumerate(state):
        neighbors = _neighbors(site)
        count = len(neighbors)
        delta2 = (
            sum(value2[state[n]] for n in neighbors) - count * value2[phase]
        )
        coupling100 = 75 if _anchor(site) else 50
        threshold100 = 5 if phase == "M" else 50 if _anchor(site) else 35
        drive_num = 2 * count * stimulus_s100[site] + coupling100 * delta2
        limit = 2 * count * threshold100
        direction = 1 if drive_num >= limit else -1 if drive_num <= -limit else 0
        index = _PHASES.index(phase)
        next_state[site] = _PHASES[max(0, min(2, index + direction))]
    return "".join(next_state)


def test_frozen_hardware_vectors_are_complete_and_exact() -> None:
    validate_vectors()
    config = Grid2DConfig(width=8, height=8, memory_decay=0.0)
    coverage: set[tuple[str, str]] = set()
    compared_ticks = 0

    for vector in build_sequences():
        model = Grid2D(vector.initial_state, config=config)
        exact_state = vector.initial_state
        assert len(exact_state) == CELLS

        for stimulus_s100 in vector.stimuli_s100:
            before = model.state_string()
            model.step([value / 100.0 for value in stimulus_s100])
            after = model.state_string()
            exact_state = _exact_step(exact_state, stimulus_s100)
            assert after == exact_state
            coverage.update(
                (left, right)
                for left, right in zip(before, after)
                if left != right
            )
            compared_ticks += 1

    assert compared_ticks == 256 * 12
    assert coverage == {("A", "M"), ("M", "C"), ("C", "M"), ("M", "A")}
