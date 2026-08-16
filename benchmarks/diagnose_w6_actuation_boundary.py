"""Diagnose why W6 erasure handoff does not recover the nine frozen `M` cases.

Diagnostic only. No amplitude, threshold, coupling, horizon, witness, or repair
mechanism is changed. The script measures the local field seen by the newly
owned `M` cell after erasure-aware handoff and classifies whether the residual
failure is opposing-field, subthreshold, timing, or rebound/oscillation.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from benchmarks.probe_witness_erasure import _is_diagnosed_mixed_erasure
from benchmarks.probe_witness_persistent import _corrupt_all, _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from benchmarks.run_w4_confirmation import _run
from morphos.witness import WitnessLaw
from morphos.witness_erasure import ErasureAwareAuthorityGrid2D
from morphos.witness_handoff import HandoffAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w6_erasure_manifest.json")
_VALUE = {"A": 0.0, "M": 0.5, "C": 1.0}


class InstrumentedErasureGrid2D(ErasureAwareAuthorityGrid2D):
    """W6 with read-only instrumentation around its unchanged transition law."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.actuation_samples: list[dict] = []
        self._seen_erasure_handoffs = 0

    def _transition_and_commit(self, stimuli: list[float]) -> None:
        sample = None
        if (
            self.selective_fence_active
            and self.latched_index is not None
            and self.latched_target is not None
            and self.erasure_handoff_events > 0
            and self.states[self.latched_index] == "M"
        ):
            index = self.latched_index
            target = self.latched_target
            direction = 1.0 if target == "C" else -1.0
            anchor = self._is_anchor(index)
            coupling = (
                self.config.anchor_coupling
                if anchor
                else self.config.adaptive_coupling
            )
            threshold = self.config.mixed_relax_threshold
            neighbors = self._neighbors(index)
            domain = self._domain(index)
            intra_factor = self.law.intra_factor(
                self.config.width, self.config.height
            )
            weighted_delta = sum(
                (
                    intra_factor
                    if self._domain(neighbor) == domain
                    else 1.0
                )
                * (_VALUE[self.states[neighbor]] - _VALUE["M"])
                for neighbor in neighbors
            ) / len(neighbors)
            neighbor_drive = coupling * weighted_delta

            mirror_components = []
            for name, phase, mirror_coupling in (
                (
                    "local",
                    self.local_mirror_states[index],
                    self.reflective_law.local_coupling,
                ),
                (
                    "domain",
                    self.domain_mirror_states[index],
                    self.reflective_law.domain_coupling,
                ),
                (
                    "system",
                    self.system_mirror_states[index],
                    self.reflective_law.system_coupling,
                ),
            ):
                suppressed = (
                    index in self.protected_targets
                    and phase != self.protected_targets[index]
                )
                component = (
                    0.0
                    if suppressed
                    else mirror_coupling * (_VALUE[phase] - _VALUE["M"])
                )
                mirror_components.append(
                    {
                        "name": name,
                        "phase": phase,
                        "suppressed": suppressed,
                        "drive": component,
                    }
                )
            mirror_drive = sum(row["drive"] for row in mirror_components)
            witness_drive = stimuli[index]
            total_drive = witness_drive + neighbor_drive + mirror_drive
            activation_before = self.activations[index]
            activation_candidate = (
                self.config.memory_decay * activation_before + total_drive
            )
            signed_total = total_drive * direction
            signed_activation = activation_candidate * direction
            sample = {
                "tick_before": self.tick,
                "index": index,
                "target": target,
                "anchor": anchor,
                "domain": list(domain),
                "domain_local_row": (index // self.config.width) % self.law.domain_size,
                "domain_local_col": (index % self.config.width) % self.law.domain_size,
                "neighbor_count": len(neighbors),
                "neighbor_same_target_count": sum(
                    self.states[n] == target for n in neighbors
                ),
                "neighbor_m_count": sum(
                    self.states[n] == "M" for n in neighbors
                ),
                "witness_drive": witness_drive,
                "neighbor_drive": neighbor_drive,
                "mirror_drive": mirror_drive,
                "mirror_components": mirror_components,
                "total_drive": total_drive,
                "signed_total_drive_toward_target": signed_total,
                "activation_before": activation_before,
                "activation_candidate": activation_candidate,
                "signed_activation_toward_target": signed_activation,
                "mixed_relax_threshold": threshold,
                "threshold_crossing_toward_target": signed_activation >= threshold,
                "new_erasure_handoff_this_tick": (
                    self.erasure_handoff_events > self._seen_erasure_handoffs
                ),
            }

        super()._transition_and_commit(stimuli)

        if sample is not None:
            sample["phase_after"] = self.states[sample["index"]]
            sample["activation_after"] = self.activations[sample["index"]]
            self.actuation_samples.append(sample)
        self._seen_erasure_handoffs = self.erasure_handoff_events


def _run_case(target: str, source: int, config, hierarchy, mirror_law, spec: dict) -> dict:
    model = InstrumentedErasureGrid2D(
        target,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(
            witness_drive=spec["witness_drive"],
            commit_delay=spec["witness_commit_delay"],
        ),
    )
    _corrupt_all(model, source)

    first_erasure_owner = None
    first_erasure_handoff_tick = None
    timeline = []
    for tick in range(1, spec["retention_horizon"] + 1):
        before = model.erasure_handoff_events
        model.step(0.0)
        if model.erasure_handoff_events > before and first_erasure_owner is None:
            first_erasure_owner = model.handoff_history[-1][1]
            first_erasure_handoff_tick = tick
        owner_phase = (
            model.states[first_erasure_owner]
            if first_erasure_owner is not None
            else None
        )
        timeline.append(
            {
                "tick": tick,
                "owner_phase": owner_phase,
                "latched_index": model.latched_index,
                "erasure_handoff_events": model.erasure_handoff_events,
                "exact": model.state_string() == target,
                "residual_hamming": sum(
                    actual != expected
                    for actual, expected in zip(model.states, target)
                ),
            }
        )

    samples = model.actuation_samples
    first = samples[0] if samples else None
    target_phase = target[first_erasure_owner] if first_erasure_owner is not None else None
    post_handoff_phases = [
        row["owner_phase"]
        for row in timeline
        if first_erasure_handoff_tick is not None
        and row["tick"] >= first_erasure_handoff_tick
    ]
    target_seen = target_phase in post_handoff_phases if target_phase else False
    exact_seen = any(row["exact"] for row in timeline)
    exact_at_8 = timeline[spec["evaluation_horizon"] - 1]["exact"]
    exact_at_12 = timeline[spec["retention_horizon"] - 1]["exact"]

    if first is None:
        classification = "handoff_without_m_sample"
    elif not first["threshold_crossing_toward_target"]:
        if first["signed_total_drive_toward_target"] <= 0:
            classification = "opposing_field"
        else:
            classification = "subthreshold_actuation"
    elif target_seen and not exact_at_12:
        classification = "rebound_or_collateral_after_endpoint"
    elif not target_seen:
        classification = "threshold_crossing_but_endpoint_not_observed"
    elif exact_seen and not exact_at_8:
        classification = "timing_or_rebound"
    else:
        classification = "actuation_sufficient"

    return {
        "source": source,
        "first_erasure_owner": first_erasure_owner,
        "first_erasure_handoff_tick": first_erasure_handoff_tick,
        "target_phase": target_phase,
        "classification": classification,
        "target_seen_after_handoff": target_seen,
        "exact_seen": exact_seen,
        "exact_at_8": exact_at_8,
        "exact_at_12": exact_at_12,
        "post_handoff_phases": post_handoff_phases,
        "first_actuation_sample": first,
        "actuation_samples": samples,
        "timeline": timeline,
    }


def run_diagnostic() -> dict:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    cases = []

    for corpus in spec["corpora"]:
        width, height = corpus["width"], corpus["height"]
        cells = width * height
        config, hierarchy = _s2_components(base, width, height)
        mirror_law = _m2_law(base)
        targets = _fixed_binary_targets(
            _sha_binary_seeds(corpus["seed"], corpus["samples"], cells),
            config,
            hierarchy,
            spec["target_discovery_steps"],
        )[: spec["max_targets"]]
        for target_index, target in enumerate(targets):
            indices = _noise_indices(
                corpus["seed"], target_index, cells, spec["trials_per_target"]
            )
            for trial_index, source in enumerate(indices):
                kwargs = dict(
                    target=target,
                    indices=[source],
                    config=config,
                    hierarchy=hierarchy,
                    m2_law=mirror_law,
                    witness_drive=spec["witness_drive"],
                    witness_commit_delay=spec["witness_commit_delay"],
                )
                w5_8 = _run(
                    HandoffAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w5_12 = _run(
                    HandoffAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                if not _is_diagnosed_mixed_erasure(w5_8, w5_12, target, source):
                    continue
                result = _run_case(
                    target, source, config, hierarchy, mirror_law, spec
                )
                result.update(
                    {
                        "width": width,
                        "height": height,
                        "seed": corpus["seed"],
                        "target_index": target_index,
                        "trial_index": trial_index,
                    }
                )
                cases.append(result)

    counts = Counter(case["classification"] for case in cases)
    first_samples = [
        case["first_actuation_sample"]
        for case in cases
        if case["first_actuation_sample"] is not None
    ]
    return {
        "schema": "cosmic-organics/w6-actuation-boundary-diagnostic-0.1",
        "diagnostic_only_no_retuning": True,
        "source_w6_head": "764cde7e01ab85252cea68417433b3fb49adc15a",
        "case_count": len(cases),
        "classification_counts": dict(sorted(counts.items())),
        "handoff_tick_counts": dict(
            sorted(Counter(case["first_erasure_handoff_tick"] for case in cases).items())
        ),
        "target_seen_after_handoff_count": sum(
            case["target_seen_after_handoff"] for case in cases
        ),
        "exact_seen_count": sum(case["exact_seen"] for case in cases),
        "exact_at_8_count": sum(case["exact_at_8"] for case in cases),
        "exact_at_12_count": sum(case["exact_at_12"] for case in cases),
        "first_sample_signed_total_drive": [
            row["signed_total_drive_toward_target"] for row in first_samples
        ],
        "first_sample_signed_activation": [
            row["signed_activation_toward_target"] for row in first_samples
        ],
        "first_sample_threshold_crossing_count": sum(
            row["threshold_crossing_toward_target"] for row in first_samples
        ),
        "cases": cases,
    }


def main() -> None:
    print(json.dumps(run_diagnostic(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
