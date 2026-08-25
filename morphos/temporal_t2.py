"""MORPHOS-T2: experimental mixed-state relaxation extension.

T2 adds a separate threshold used only while a cell is in the intermediate M
state. This is an algorithmic hypothesis for testing the mixed-state dead zone;
it is not calibrated to a physical material mechanism.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable, Sequence

from morphos.simulator import Phase

_PHASES = (Phase.AMORPHOUS, Phase.MIXED, Phase.CRYSTALLINE)


@dataclass(frozen=True)
class T2Config:
    coupling: float = 0.35
    crystallize_threshold: float = 0.35
    amorphize_threshold: float = 0.35
    memory_decay: float = 0.8
    mixed_relax_threshold: float = 0.1
    reset_on_transition: bool = True

    def __post_init__(self) -> None:
        if self.coupling < 0:
            raise ValueError("coupling must be non-negative")
        if self.crystallize_threshold <= 0 or self.amorphize_threshold <= 0:
            raise ValueError("thresholds must be positive")
        if self.mixed_relax_threshold <= 0:
            raise ValueError("mixed_relax_threshold must be positive")
        if not 0.0 <= self.memory_decay <= 1.0:
            raise ValueError("memory_decay must be between 0 and 1")


@dataclass(frozen=True)
class T2Cell:
    phase: Phase = Phase.AMORPHOUS
    activation: float = 0.0
    transitions: int = 0


class T2Lattice:
    """Temporal lattice with a dedicated relaxation threshold for M cells."""

    def __init__(
        self,
        size: int,
        *,
        initial: Phase | Sequence[Phase] = Phase.AMORPHOUS,
        config: T2Config | None = None,
    ) -> None:
        if size <= 0:
            raise ValueError("size must be positive")
        self.config = config or T2Config()
        if isinstance(initial, Phase):
            phases = [initial] * size
        else:
            phases = list(initial)
            if len(phases) != size:
                raise ValueError("initial phase sequence length must equal size")
        self.cells = [T2Cell(phase=phase) for phase in phases]
        self.tick = 0
        self.max_abs_activation_seen = 0.0

    def _neighbor_mean(self, index: int) -> float:
        neighbors: list[float] = []
        if index > 0:
            neighbors.append(self.cells[index - 1].phase.value01)
        if index + 1 < len(self.cells):
            neighbors.append(self.cells[index + 1].phase.value01)
        return sum(neighbors) / len(neighbors) if neighbors else self.cells[index].phase.value01

    @staticmethod
    def _step_phase(phase: Phase, direction: int) -> Phase:
        index = _PHASES.index(phase)
        next_index = max(0, min(len(_PHASES) - 1, index + direction))
        return _PHASES[next_index]

    def step(self, stimuli: float | Sequence[float]) -> None:
        if isinstance(stimuli, (int, float)):
            stimulus_values = [float(stimuli)] * len(self.cells)
        else:
            stimulus_values = [float(value) for value in stimuli]
            if len(stimulus_values) != len(self.cells):
                raise ValueError("stimulus sequence length must equal lattice size")

        next_cells: list[T2Cell] = []
        for index, (cell, stimulus) in enumerate(zip(self.cells, stimulus_values)):
            neighborhood = self._neighbor_mean(index)
            instant_drive = stimulus + self.config.coupling * (
                neighborhood - cell.phase.value01
            )
            activation = self.config.memory_decay * cell.activation + instant_drive
            self.max_abs_activation_seen = max(self.max_abs_activation_seen, abs(activation))

            if cell.phase is Phase.MIXED:
                positive_threshold = self.config.mixed_relax_threshold
                negative_threshold = self.config.mixed_relax_threshold
            else:
                positive_threshold = self.config.crystallize_threshold
                negative_threshold = self.config.amorphize_threshold

            direction = 0
            if activation >= positive_threshold:
                direction = 1
            elif activation <= -negative_threshold:
                direction = -1

            phase = self._step_phase(cell.phase, direction)
            changed = phase != cell.phase
            if changed and self.config.reset_on_transition:
                activation = 0.0

            next_cells.append(
                T2Cell(
                    phase=phase,
                    activation=activation,
                    transitions=cell.transitions + int(changed),
                )
            )

        self.cells = next_cells
        self.tick += 1

    def run(self, pulses: Iterable[float | Sequence[float]]) -> None:
        for pulse in pulses:
            self.step(pulse)

    @property
    def transition_count(self) -> int:
        return sum(cell.transitions for cell in self.cells)

    @property
    def order_parameter(self) -> float:
        return sum(cell.phase.value01 for cell in self.cells) / len(self.cells)

    def phase_string(self) -> str:
        return "".join(cell.phase.value for cell in self.cells)

    def snapshot(self) -> dict:
        return {
            "protocol_version": "MORPHOS-T2/0.1",
            "tick": self.tick,
            "config": asdict(self.config),
            "cells": [
                {
                    "phase": cell.phase.value,
                    "activation": round(cell.activation, 12),
                    "transitions": cell.transitions,
                }
                for cell in self.cells
            ],
            "metrics": {
                "order_parameter": round(self.order_parameter, 12),
                "transition_count": self.transition_count,
                "max_abs_activation_seen": round(self.max_abs_activation_seen, 12),
            },
        }

    def state_digest(self) -> str:
        payload = json.dumps(
            self.snapshot(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
