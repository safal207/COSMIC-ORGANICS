"""Development-only probe for MORPHOS-W5 syndrome handoff.

Uses the already diagnosed worst W4 confirmation corpus. No W4 parameter is
retuned; the only mechanism change is moving repair ownership after the current
owner is corrected and parity uniquely localizes a different binary cell.
"""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.probe_witness_persistent import _manifest
from benchmarks.run_multimirror import _fixed_binary_targets, _m2_law, _noise_indices, _s2_components, _sha_binary_seeds
from benchmarks.run_w4_confirmation import _run
from morphos.witness_handoff import HandoffAuthorityGrid2D
from morphos.witness_selective import SelectiveAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w5_handoff_manifest.json")


def run_probe() -> dict:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    corpus = spec["corpus"]
    width, height = corpus["width"], corpus["height"]
    cells = width * height
    base = _manifest()
    config, hierarchy = _s2_components(base, width, height)
    mirror_law = _m2_law(base)
    targets = _fixed_binary_targets(
        _sha_binary_seeds(corpus["seed"], corpus["samples"], cells),
        config, hierarchy, spec["target_discovery_steps"],
    )[: spec["max_targets"]]

    counts = {
        "trials": 0,
        "w4_success_8": 0,
        "w5_success_8": 0,
        "w5_success_12": 0,
        "w4_collateral_failures": 0,
        "w5_rescued_collateral_failures": 0,
        "w4_successes_regressed": 0,
        "w5_handoff_trials": 0,
        "w5_corrupt_witness_success_8": 0,
        "w5_zero_success_8": 0,
        "w4_zero_success_8": 0,
        "w5_primary_success_8": 0,
        "w4_primary_success_8": 0,
    }

    for target_index, target in enumerate(targets):
        indices = _noise_indices(corpus["seed"], target_index, cells, corpus["trials_per_target"])
        for index in indices:
            one = [index]
            common_kwargs = dict(
                target=target, indices=one, config=config, hierarchy=hierarchy,
                m2_law=mirror_law, witness_drive=spec["witness_drive"],
                witness_commit_delay=spec["witness_commit_delay"],
            )
            w4 = _run(SelectiveAuthorityGrid2D, horizon=spec["evaluation_horizon"], **common_kwargs)
            w5 = _run(HandoffAuthorityGrid2D, horizon=spec["evaluation_horizon"], **common_kwargs)
            w5_12 = _run(HandoffAuthorityGrid2D, horizon=spec["retention_horizon"], **common_kwargs)
            corrupt = _run(HandoffAuthorityGrid2D, horizon=spec["evaluation_horizon"], corrupt_witness=True, **common_kwargs)
            w5_zero = _run(HandoffAuthorityGrid2D, horizon=spec["evaluation_horizon"], zero_drive=True, **common_kwargs)
            w4_zero = _run(SelectiveAuthorityGrid2D, horizon=spec["evaluation_horizon"], zero_drive=True, **common_kwargs)
            w5_primary = _run(HandoffAuthorityGrid2D, horizon=spec["evaluation_horizon"], common=False, **common_kwargs)
            w4_primary = _run(SelectiveAuthorityGrid2D, horizon=spec["evaluation_horizon"], common=False, **common_kwargs)

            w4_ok = w4.state_string() == target
            w5_ok = w5.state_string() == target
            w5_12_ok = w5_12.state_string() == target
            collateral_failure = (not w4_ok) and w4.states[index] == target[index]

            counts["trials"] += 1
            counts["w4_success_8"] += int(w4_ok)
            counts["w5_success_8"] += int(w5_ok)
            counts["w5_success_12"] += int(w5_12_ok)
            counts["w4_collateral_failures"] += int(collateral_failure)
            counts["w5_rescued_collateral_failures"] += int(collateral_failure and w5_ok)
            counts["w4_successes_regressed"] += int(w4_ok and not w5_ok)
            counts["w5_handoff_trials"] += int(w5.handoff_events > 0)
            counts["w5_corrupt_witness_success_8"] += int(corrupt.state_string() == target)
            counts["w5_zero_success_8"] += int(w5_zero.state_string() == target)
            counts["w4_zero_success_8"] += int(w4_zero.state_string() == target)
            counts["w5_primary_success_8"] += int(w5_primary.state_string() == target)
            counts["w4_primary_success_8"] += int(w4_primary.state_string() == target)

    n = counts["trials"]
    rate = lambda key: counts[key] / n
    summary = {
        "w4_recovery_at_8": rate("w4_success_8"),
        "w5_recovery_at_8": rate("w5_success_8"),
        "w5_recovery_at_12": rate("w5_success_12"),
        "gain_vs_w4_at_8": rate("w5_success_8") - rate("w4_success_8"),
        "collateral_failures": counts["w4_collateral_failures"],
        "collateral_failures_rescued": counts["w5_rescued_collateral_failures"],
        "previous_w4_successes_regressed": counts["w4_successes_regressed"],
        "handoff_trial_fraction": rate("w5_handoff_trials"),
        "retention_delta_12_minus_8": rate("w5_success_12") - rate("w5_success_8"),
        "causal_drop_when_witness_corrupted": rate("w5_success_8") - rate("w5_corrupt_witness_success_8"),
        "zero_drive_exact_w4": counts["w5_zero_success_8"] == counts["w4_zero_success_8"],
        "primary_only_delta_vs_w4": rate("w5_primary_success_8") - rate("w4_primary_success_8"),
    }
    gate = spec["predeclared_gates"]
    passes = (
        summary["collateral_failures_rescued"] >= gate["minimum_collateral_failures_rescued"]
        and summary["previous_w4_successes_regressed"] <= gate["maximum_previous_w4_successes_regressed"]
        and summary["w5_recovery_at_8"] >= gate["minimum_overall_recovery_at_8"]
        and summary["retention_delta_12_minus_8"] >= -gate["maximum_retention_drop_8_to_12"]
        and summary["causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted"]
        and summary["primary_only_delta_vs_w4"] >= gate["minimum_primary_only_delta_vs_w4"]
        and (summary["zero_drive_exact_w4"] if gate["zero_drive_must_match_w4"] else True)
    )
    return {
        "schema": spec["schema"],
        "development_only": True,
        "retunes_w4": False,
        "criteria": gate,
        "summary": summary,
        "passes": passes,
        "negative_evidence_boundary": spec["negative_evidence_boundary"],
    }


def main() -> None:
    print(json.dumps(run_probe(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
