"""MORPHOS-W8.1 evidence-bounded path margin completion.

W8-v0 completed only the first binary threshold. Its frozen failure trace showed
all four remaining cases entering M and then returning to the still-owned wrong
binary endpoint without ever reaching the independently witnessed target.

W8.1 preserves W8-v0 exactly for wrong binary entry and extends the same
minimum-representable deficit rule to M while the *same initial repair
obligation* remains the sole protected target. It uses the existing
``mixed_relax_threshold``; no witness amplitude, threshold, coupling, decoder,
commit delay, seed, or horizon is retuned. The extension stops at the target
endpoint and is disabled once ownership expands into W5-W7 handoff/repair-set
semantics.

Classical deterministic algorithmic recovery control only; not a physical
energy model and not a quantum/biological mechanism.
"""
from __future__ import annotations

import math

from morphos.witness_margin_completion import MarginCompletionAuthorityGrid2D
from morphos.witness_selective import _VALUE


class PathCompletionAuthorityGrid2D(MarginCompletionAuthorityGrid2D):
    """Keep the witnessed direction margin-complete until the entry owner lands."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.path_completion_m_events = 0
        self.path_completion_binary_events = 0

    def _entry_margin_completion(self, stimuli: list[float]) -> None:
        # Preserve the frozen W8-v0 binary-entry primitive byte-for-behavior.
        if self.latched_index is None:
            return super()._entry_margin_completion(stimuli)
        index = self.latched_index
        phase = self.states[index]
        if phase != "M":
            before = self.margin_completion_events
            super()._entry_margin_completion(stimuli)
            self.path_completion_binary_events += self.margin_completion_events - before
            return

        if (
            not self.selective_fence_active
            or len(self.protected_targets) != 1
            or self.latched_target not in ("A", "C")
            or self.protected_targets.get(index) != self.latched_target
        ):
            return

        target = self.latched_target
        anchor = self._is_anchor(index)
        coupling = (
            self.config.anchor_coupling if anchor else self.config.adaptive_coupling
        )
        neighbors = self._neighbors(index)
        domain = self._domain(index)
        intra_factor = self.law.intra_factor(
            self.config.width, self.config.height
        )
        weighted_delta = sum(
            (intra_factor if self._domain(neighbor) == domain else 1.0)
            * (_VALUE[self.states[neighbor]] - _VALUE[phase])
            for neighbor in neighbors
        ) / len(neighbors)
        mirror_drive = self._effective_protected_mirror_drive(
            index=index, phase=phase, target=target
        )
        projected_activation = (
            self.config.memory_decay * self.activations[index]
            + stimuli[index]
            + coupling * weighted_delta
            + mirror_drive
        )
        direction = 1.0 if target == "C" else -1.0
        toward_target = direction * projected_activation
        threshold = self.config.mixed_relax_threshold
        if toward_target >= threshold:
            return

        required_toward = math.nextafter(threshold, math.inf)
        completion = required_toward - toward_target
        if completion <= 0.0:
            return
        stimuli[index] += direction * completion
        self.margin_completion_events += 1
        self.margin_completion_total += completion
        self.margin_completion_max = max(self.margin_completion_max, completion)
        self.path_completion_m_events += 1
        if anchor:
            self.margin_completion_anchor_events += 1
        else:
            self.margin_completion_adaptive_events += 1
