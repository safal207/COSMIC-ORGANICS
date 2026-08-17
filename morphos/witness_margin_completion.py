"""MORPHOS-W8 evidence-bounded entry margin completion.

W7's frozen residual diagnostic found a narrower actuation boundary: every
remaining single-bit common-mode miss was an independently localized anchor
source whose projected corrective activation remained below the unchanged
transition threshold.

W8 does not raise witness amplitude globally and does not retune thresholds,
couplings, commit delays, decoder, or horizons. During a quiescent repair only,
while there is exactly one initial binary repair obligation, it computes the
already-authorized projected activation after W7's bounded witness drive and
adds only the minimum representable support required to cross the existing
threshold. Once the source reaches its endpoint, W5-W7 handoff/erasure/repair-
set semantics proceed unchanged.

This is a classical algorithmic recovery-control experiment. The completion
term is not a physical energy model and carries no quantum/biological claim.
"""
from __future__ import annotations

import math

from morphos.witness_repair_set import RepairSetAuthorityGrid2D
from morphos.witness_selective import _VALUE


class MarginCompletionAuthorityGrid2D(RepairSetAuthorityGrid2D):
    """Complete only a witnessed initial binary obligation's threshold deficit."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.margin_completion_events = 0
        self.margin_completion_total = 0.0
        self.margin_completion_max = 0.0
        self.margin_completion_anchor_events = 0
        self.margin_completion_adaptive_events = 0

    def _effective_protected_mirror_drive(
        self, *, index: int, phase: str, target: str
    ) -> float:
        """Mirror contribution after W5's protected-target filter, without counters."""
        law = self.reflective_law
        total = 0.0
        for mirror_phase, coupling in (
            (self.local_mirror_states[index], law.local_coupling),
            (self.domain_mirror_states[index], law.domain_coupling),
            (self.system_mirror_states[index], law.system_coupling),
        ):
            # W5/W7 suppress any protected mirror claim that contradicts the
            # independently established endpoint.
            if mirror_phase != target:
                continue
            total += coupling * (_VALUE[mirror_phase] - _VALUE[phase])
        return total

    def _entry_margin_completion(self, stimuli: list[float]) -> None:
        if (
            not self.selective_fence_active
            or len(self.protected_targets) != 1
            or self.latched_index is None
            or self.latched_target is None
        ):
            return

        index = self.latched_index
        target = self.latched_target
        if self.protected_targets.get(index) != target or target not in ("A", "C"):
            return

        phase = self.states[index]
        # Keep the scope binary and entry-only. W6's M-erasure and W7's repair
        # set remain the authority for transition-state and post-handoff cases.
        if phase not in ("A", "C") or phase == target:
            return
        if phase == "A" and target != "C":
            return
        if phase == "C" and target != "A":
            return

        anchor = self._is_anchor(index)
        threshold = (
            self.config.anchor_threshold if anchor else self.config.adaptive_threshold
        )
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
        if toward_target >= threshold:
            return

        # No tunable rescue amplitude: request the smallest representable
        # activation strictly above the already-existing threshold.
        required_toward = math.nextafter(threshold, math.inf)
        completion = required_toward - toward_target
        if completion <= 0.0:
            return
        stimuli[index] += direction * completion
        self.margin_completion_events += 1
        self.margin_completion_total += completion
        self.margin_completion_max = max(self.margin_completion_max, completion)
        if anchor:
            self.margin_completion_anchor_events += 1
        else:
            self.margin_completion_adaptive_events += 1

    def _apply_latched_drive(self, stimuli: list[float]) -> None:
        # W7 establishes the bounded evidence-backed repair drive first.
        super()._apply_latched_drive(stimuli)
        # W8 only fills any remaining threshold deficit at the initial owner.
        self._entry_margin_completion(stimuli)
