"""Diagnostic-only arithmetic trace for the sole frozen W8.1 residual.

No mechanism changes. Instrument the exact activation expression consumed by
_transition_and_commit after W8.1 has already modified stimuli, then compare it
to an algebraically equivalent reordered expression at the one-ULP threshold
boundary.
"""
from __future__ import annotations

import json

from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.witness import WitnessLaw
from morphos.witness_path_completion import PathCompletionAuthorityGrid2D
from morphos.witness_selective import _VALUE


class TracedPathCompletionGrid(PathCompletionAuthorityGrid2D):
    def __init__(self, *args, trace_index: int, **kwargs):
        super().__init__(*args, **kwargs)
        self.trace_index = trace_index
        self.numeric_trace: list[dict] = []

    def _transition_and_commit(self, stimuli: list[float]) -> None:
        index = self.trace_index
        phase = self.states[index]
        target = self.protected_targets.get(index)
        if target in ("A", "C") and phase != target:
            anchor = self._is_anchor(index)
            coupling = self.config.anchor_coupling if anchor else self.config.adaptive_coupling
            regular_threshold = self.config.anchor_threshold if anchor else self.config.adaptive_threshold
            threshold = self.config.mixed_relax_threshold if phase == "M" else regular_threshold
            neighbors = self._neighbors(index)
            domain = self._domain(index)
            intra_factor = self.law.intra_factor(self.config.width, self.config.height)
            weighted_delta = sum(
                (intra_factor if self._domain(n) == domain else 1.0)
                * (_VALUE[self.states[n]] - _VALUE[phase])
                for n in neighbors
            ) / len(neighbors)
            mirror_drive = self._effective_protected_mirror_drive(
                index=index, phase=phase, target=target
            )
            # This grouping mirrors SelectiveAuthorityGrid2D exactly.
            actual_drive = stimuli[index] + coupling * weighted_delta + mirror_drive
            actual_activation = self.config.memory_decay * self.activations[index] + actual_drive
            # This grouping matches the projection used by W8/W8.1.
            projected_reordered = (
                self.config.memory_decay * self.activations[index]
                + stimuli[index]
                + coupling * weighted_delta
                + mirror_drive
            )
            direction = 1.0 if target == "C" else -1.0
            actual_toward = direction * actual_activation
            projected_toward = direction * projected_reordered
            self.numeric_trace.append(
                {
                    "phase": phase,
                    "target": target,
                    "stimulus_after_completion": stimuli[index],
                    "weighted_neighbor_delta": weighted_delta,
                    "coupling": coupling,
                    "mirror_drive": mirror_drive,
                    "activation_before": self.activations[index],
                    "threshold": threshold,
                    "actual_toward": actual_toward,
                    "projected_reordered_toward": projected_toward,
                    "actual_minus_threshold": actual_toward - threshold,
                    "projected_minus_threshold": projected_toward - threshold,
                    "grouping_delta": actual_toward - projected_toward,
                    "completion_events": self.margin_completion_events,
                    "m_completion_events": self.path_completion_m_events,
                }
            )
        super()._transition_and_commit(stimuli)


def run_diagnostic() -> dict:
    base = _manifest()
    width = 7
    seed = 202608164012
    target_index = 3
    trial_index = 1
    config, hierarchy = _s2_components(base, width, width)
    targets = _fixed_binary_targets(
        _sha_binary_seeds(seed, 64, width * width), config, hierarchy, 6
    )[:8]
    target = targets[target_index]
    source = _noise_indices(seed, target_index, width * width, 6)[trial_index]
    model = TracedPathCompletionGrid(
        target,
        trace_index=source,
        config=config,
        law=hierarchy,
        reflective_law=_m2_law(base),
        witness_law=WitnessLaw(witness_drive=0.25, commit_delay=8),
    )
    _corrupt_all(model, source)
    phase_timeline = [model.states[source]]
    for _ in range(12):
        model.step(0.0)
        phase_timeline.append(model.states[source])

    m_rows = [row for row in model.numeric_trace if row["phase"] == "M"]
    below_actual = [row for row in m_rows if row["actual_minus_threshold"] < 0]
    projected_nonnegative_actual_negative = [
        row
        for row in m_rows
        if row["projected_minus_threshold"] >= 0 and row["actual_minus_threshold"] < 0
    ]
    return {
        "schema": "cosmic-organics/w81-numeric-contract-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_w81_head": "7d8302fa872eca8cd04ff6a8df0887ff5e160cc4",
        "case": {
            "width": width,
            "seed": seed,
            "target_index": target_index,
            "trial_index": trial_index,
            "source": source,
            "target_endpoint": target[source],
            "phase_timeline": phase_timeline,
            "exact_at_12": model.state_string() == target,
            "completion_events": model.margin_completion_events,
            "m_completion_events": model.path_completion_m_events,
        },
        "m_transition_rows": m_rows,
        "summary": {
            "m_rows": len(m_rows),
            "actual_below_threshold_rows": len(below_actual),
            "projected_nonnegative_but_actual_negative_rows": len(projected_nonnegative_actual_negative),
            "minimum_actual_minus_threshold": min((r["actual_minus_threshold"] for r in m_rows), default=None),
            "minimum_projected_minus_threshold": min((r["projected_minus_threshold"] for r in m_rows), default=None),
            "maximum_absolute_grouping_delta": max((abs(r["grouping_delta"]) for r in m_rows), default=0.0),
        },
        "decision_contract": "if reordered projection is >= threshold while exact transition grouping is < threshold, factor a single shared activation projection primitive before considering stronger recovery authority",
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
