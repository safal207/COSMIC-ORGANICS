"""Deterministic MORPHOS-0 phase-transition reference model.

This is a phenomenological computational model, not a calibrated simulation of
any specific physical material.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from typing import Iterable, Sequence


class Phase(str, Enum):
    AMORPHOUS = "A"
    MIXED = "M"
    CRYSTALLINE = "C"

    @property
    def value01(self) -> float:
        return {
            Phase.AMORPHOUS: 0.0,
            Phase.MIXED: 0.5,
            Phase.CRYSTALLINE: 1.0,
        }[self]


_PHASES = (Phase.AMORPHOUS, Phase.MIXED, Phase.CRYSTALLINE)


@dataclass(frozen=True)
class SimulationConfig:
    coupling: float = 0.35
    crystallize_threshold: float = 0.35
    amorphize_threshold: float = 0.35

    def __post_init__(self) -> None:
        if self.coupling < 0:
            raise ValueError("coupling must be non-negative")
        if self.crystallize_threshold <= 0 or self.amorphize_threshold <= 0:
            raise ValueError("thresholds must be positive")


@dataclass(frozen=True)
class Cell:
    phase: Phase = Phase.AMORPHOUS
    energy: float = 0.0
    transitions: int = 0

    def __post_init__(self) -> None:
        if self.energy < 0:
            raise ValueError("energy must be non-negative")
        if self.transitions < 0:
            raise ValueError("transitions must be non-negative")


class Lattice:
    def __init__(
        self,
        size: int,
        *,
        initial: Phase | Sequence[Phase] = Phase.AMORPHOUS,
        config: SimulationConfig | None = None,
    ) -> None:
        if size <= 0:
            raise ValueError("size must be positive")
        self.config = config or SimulationConfig()
        if isinstance(initial, Phase):
            phases = [initial] * size
        else:
            phases = list(initial)
            if len(phases) != size:
                raise ValueError("initial phase sequence length must equal size")
        self.cells = [Cell(phase=p) for p in phases]
        self.tick = 0

    def _neighbor_mean(self, index: int) -> float:
        neighbors: list[float] = []
        if index > 0:
            neighbors.append(self.cells[index - 1].phase.value01)
        if index + 1 < len(self.cells):
            neighbors.append(self.cells[index + 1].phase.value01)
        return sum(neighbors) / len(neighbors) if neighbors else self.cells[index].phase.value01

    @staticmethod
    def _step_phase(phase: Phase, direction: int) -> Phase:
        idx = _PHASES.index(phase)
        next_idx = max(0, min(len(_PHASES) - 1, idx + direction))
        return _PHASES[next_idx]

    def step(self, stimuli: float | Sequence[float]) -> None:
        if isinstance(stimuli, (int, float)):
            stimulus_values = [float(stimuli)] * len(self.cells)
        else:
            stimulus_values = [float(v) for v in stimuli]
            if len(stimulus_values) != len(self.cells):
                raise ValueError("stimulus sequence length must equal lattice size")

        next_cells: list[Cell] = []
        for i, (cell, stimulus) in enumerate(zip(self.cells, stimulus_values)):
            neighbor_mean = self._neighbor_mean(i)
            drive = stimulus + self.config.coupling * (
                neighbor_mean - cell.phase.value01
            )

            direction = 0
            if drive >= self.config.crystallize_threshold:
                direction = 1
            elif drive <= -self.config.amorphize_threshold:
                direction = -1

            phase = self._step_phase(cell.phase, direction)
            changed = int(phase is not cell.phase)
            next_cells.append(
                Cell(
                    phase=phase,
                    energy=abs(drive),
                    transitions=cell.transitions + changed,
                )
            )

        self.cells = next_cells
        self.tick += 1

    def run(self, pulses: Iterable[float | Sequence[float]]) -> None:
        for pulse in pulses:
            self.step(pulse)

    @property
    def order_parameter(self) -> float:
        return sum(cell.phase.value01 for cell in self.cells) / len(self.cells)

    @property
    def transition_count(self) -> int:
        return sum(cell.transitions for cell in self.cells)

    def phase_string(self) -> str:
        return "".join(cell.phase.value for cell in self.cells)

    def snapshot(self) -> dict:
        return {
            "protocol_version": "MORPHOS-0/0.1",
            "tick": self.tick,
            "config": asdict(self.config),
            "cells": [
                {
                    "phase": cell.phase.value,
                    "energy": round(cell.energy, 12),
                    "transitions": cell.transitions,
                }
                for cell in self.cells
            ],
            "metrics": {
                "order_parameter": round(self.order_parameter, 12),
                "transition_count": self.transition_count,
            },
        }

    def state_digest(self) -> str:
        payload = json.dumps(
            self.snapshot(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def demo() -> dict:
    lattice = Lattice(size=9)
    pulses = [0.45, 0.45, 0.10, -0.20, 0.45]
    lattice.run(pulses)
    result = lattice.snapshot()
    result["state_digest"] = lattice.state_digest()
    return result


if __name__ == "__main__":
    print(json.dumps(demo(), indent=2, sort_keys=True))
