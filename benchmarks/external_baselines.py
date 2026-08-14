"""Simple external algorithmic baselines for P1 falsification."""
from __future__ import annotations

_PHASES = ("A", "M", "C")


class LeakyThreeState:
    """A minimal software state machine with a decaying signed accumulator."""

    def __init__(self, size: int, *, memory_decay: float, threshold: float):
        self.states = ["A"] * size
        self.activations = [0.0] * size
        self.memory_decay = memory_decay
        self.threshold = threshold
        self.transitions = 0

    def step(self, stimulus: float) -> None:
        for index in range(len(self.states)):
            activation = self.memory_decay * self.activations[index] + float(stimulus)
            state_index = _PHASES.index(self.states[index])
            direction = 0
            if activation >= self.threshold:
                direction = 1
            elif activation <= -self.threshold:
                direction = -1
            next_index = max(0, min(len(_PHASES) - 1, state_index + direction))
            if next_index != state_index:
                self.transitions += 1
                activation = 0.0
            self.states[index] = _PHASES[next_index]
            self.activations[index] = activation

    def run(self, pulses: list[float]) -> None:
        for pulse in pulses:
            self.step(pulse)

    def state_string(self) -> str:
        return "".join(self.states)


class MajorityCA:
    """Binary nearest-neighbor majority rule; ties preserve the current state."""

    def __init__(self, initial: str):
        if any(value not in {"A", "C"} for value in initial):
            raise ValueError("MajorityCA accepts only A/C states")
        self.states = list(initial)
        self.transitions = 0

    def step(self) -> None:
        next_states = self.states.copy()
        for index, current in enumerate(self.states):
            neighbors: list[str] = []
            if index > 0:
                neighbors.append(self.states[index - 1])
            if index + 1 < len(self.states):
                neighbors.append(self.states[index + 1])
            crystalline = neighbors.count("C")
            amorphous = neighbors.count("A")
            if crystalline > amorphous:
                next_states[index] = "C"
            elif amorphous > crystalline:
                next_states[index] = "A"
            else:
                next_states[index] = current
        self.transitions += sum(a != b for a, b in zip(self.states, next_states))
        self.states = next_states

    def run(self, steps: int) -> None:
        for _ in range(steps):
            self.step()

    def state_string(self) -> str:
        return "".join(self.states)
