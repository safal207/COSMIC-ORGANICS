"""Frozen independent confirmation for MORPHOS-W5 syndrome handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.probe_witness_persistent import _manifest
from benchmarks.run_multimirror import _fixed_binary_targets, _m2_law, _noise_indices, _s2_components, _sha_binary_seeds
from benchmarks.run_w4_confirmation import _run
from morphos.witness import WitnessLaw
from morphos.witness_handoff import HandoffAuthorityGrid2D
from morphos.witness_selective import SelectiveAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w5_confirmation_manifest.json")


def _protocol() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _adaptation(config, hierarchy, mirror_law, cells: int, protocol: dict) -> bool:
    model = HandoffAuthorityGrid2D(
        "A" * cells,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(
            witness_drive=protocol["witness_drive"],
            commit_delay=protocol["witness_commit_delay"],
        ),
    )
    initial = model.witness_signature()
    model.run([2.0] * 18)
    model.run([0.0] * 16)
    expected = "C" * cells
    return (
        model.state_string() == expected
        and model.local_mirror_string() == expected
        and model.domain_mirror_string() == expected
        and model.system_mirror_string() == expected
        and model.witness_signature() != initial
    )


def _corpus(spec: dict, protocol: dict) -> dict:
    base = _manifest()
    width, height = spec["width"], spec["height"]
    cells = width * height
    config, hierarchy = _s2_components(base, width, height)
    mirror_law = _m2_law(base)
    targets = _fixed_binary_targets(
        _sha_binary_seeds(spec["seed"], spec["samples"], cells),
        config, hierarchy, protocol["target_discovery_steps"],
    )[: protocol["max_targets"]]
    if not targets:
        raise RuntimeError("W5 confirmation corpus produced no binary fixed targets")

    counts = {
        "trials": 0,
        "w4_8": 0,
        "w5_8": 0,
        "w5_12": 0,
        "regressed": 0,
        "w4_collateral_failures": 0,
        "rescued_collateral_failures": 0,
        "handoff_trials": 0,
        "corrupt_8": 0,
        "w4_zero_8": 0,
        "w5_zero_8": 0,
        "w4_primary_8": 0,
        "w5_primary_8": 0,
    }
    for target_index, target in enumerate(targets):
        indices = _noise_indices(spec["seed"], target_index, cells, protocol["trials_per_target"])
        for index in indices:
            one = [index]
            kw = dict(
                target=target, indices=one, config=config, hierarchy=hierarchy,
                m2_law=mirror_law, witness_drive=protocol["witness_drive"],
                witness_commit_delay=protocol["witness_commit_delay"],
            )
            w4 = _run(SelectiveAuthorityGrid2D, horizon=protocol["evaluation_horizon"], **kw)
            w5 = _run(HandoffAuthorityGrid2D, horizon=protocol["evaluation_horizon"], **kw)
            w5_12 = _run(HandoffAuthorityGrid2D, horizon=protocol["retention_horizon"], **kw)
            corrupt = _run(HandoffAuthorityGrid2D, horizon=protocol["evaluation_horizon"], corrupt_witness=True, **kw)
            w4_zero = _run(SelectiveAuthorityGrid2D, horizon=protocol["evaluation_horizon"], zero_drive=True, **kw)
            w5_zero = _run(HandoffAuthorityGrid2D, horizon=protocol["evaluation_horizon"], zero_drive=True, **kw)
            w4_primary = _run(SelectiveAuthorityGrid2D, horizon=protocol["evaluation_horizon"], common=False, **kw)
            w5_primary = _run(HandoffAuthorityGrid2D, horizon=protocol["evaluation_horizon"], common=False, **kw)

            w4_ok = w4.state_string() == target
            w5_ok = w5.state_string() == target
            collateral = (not w4_ok) and w4.states[index] == target[index]
            counts["trials"] += 1
            counts["w4_8"] += int(w4_ok)
            counts["w5_8"] += int(w5_ok)
            counts["w5_12"] += int(w5_12.state_string() == target)
            counts["regressed"] += int(w4_ok and not w5_ok)
            counts["w4_collateral_failures"] += int(collateral)
            counts["rescued_collateral_failures"] += int(collateral and w5_ok)
            counts["handoff_trials"] += int(w5.handoff_events > 0)
            counts["corrupt_8"] += int(corrupt.state_string() == target)
            counts["w4_zero_8"] += int(w4_zero.state_string() == target)
            counts["w5_zero_8"] += int(w5_zero.state_string() == target)
            counts["w4_primary_8"] += int(w4_primary.state_string() == target)
            counts["w5_primary_8"] += int(w5_primary.state_string() == target)

    n = counts["trials"]
    rate = lambda key: counts[key] / n
    return {
        "width": width,
        "height": height,
        "seed": spec["seed"],
        "trials": n,
        "w4_recovery_at_8": rate("w4_8"),
        "w5_recovery_at_8": rate("w5_8"),
        "w5_recovery_at_12": rate("w5_12"),
        "delta_vs_w4_at_8": rate("w5_8") - rate("w4_8"),
        "previous_w4_successes_regressed": counts["regressed"],
        "retention_delta_12_minus_8": rate("w5_12") - rate("w5_8"),
        "causal_drop_when_witness_corrupted": rate("w5_8") - rate("corrupt_8"),
        "primary_only_delta_vs_w4": rate("w5_primary_8") - rate("w4_primary_8"),
        "zero_drive_exact_w4": counts["w5_zero_8"] == counts["w4_zero_8"],
        "handoff_trial_fraction": rate("handoff_trials"),
        "w4_collateral_failures": counts["w4_collateral_failures"],
        "rescued_collateral_failures": counts["rescued_collateral_failures"],
    }


def run_confirmation() -> dict:
    protocol = _protocol()
    rows = [_corpus(spec, protocol) for spec in protocol["confirmation_corpora"]]
    gate = protocol["predeclared_gates"]
    collateral_total = sum(r["w4_collateral_failures"] for r in rows)
    rescued_total = sum(r["rescued_collateral_failures"] for r in rows)
    base = _manifest()
    adaptation = {}
    for width, height in sorted({(r["width"], r["height"]) for r in rows}):
        config, hierarchy = _s2_components(base, width, height)
        adaptation[f"{width}x{height}"] = _adaptation(config, hierarchy, _m2_law(base), width * height, protocol)

    summary = {
        "minimum_w5_recovery_at_8": min(r["w5_recovery_at_8"] for r in rows),
        "minimum_w5_recovery_at_12": min(r["w5_recovery_at_12"] for r in rows),
        "minimum_delta_vs_w4_at_8": min(r["delta_vs_w4_at_8"] for r in rows),
        "maximum_previous_w4_successes_regressed": max(r["previous_w4_successes_regressed"] for r in rows),
        "minimum_retention_delta_12_minus_8": min(r["retention_delta_12_minus_8"] for r in rows),
        "minimum_causal_drop_when_witness_corrupted": min(r["causal_drop_when_witness_corrupted"] for r in rows),
        "minimum_primary_only_delta_vs_w4": min(r["primary_only_delta_vs_w4"] for r in rows),
        "zero_drive_exact_w4": all(r["zero_drive_exact_w4"] for r in rows),
        "pooled_w4_collateral_failures": collateral_total,
        "pooled_collateral_failures_rescued": rescued_total,
        "pooled_collateral_rescue_fraction": rescued_total / collateral_total if collateral_total else 1.0,
        "adaptation_by_size": adaptation,
    }
    passes = (
        summary["minimum_w5_recovery_at_8"] >= gate["minimum_w5_recovery_at_8_every_corpus"]
        and summary["minimum_w5_recovery_at_12"] >= gate["minimum_w5_recovery_at_12_every_corpus"]
        and summary["minimum_delta_vs_w4_at_8"] >= gate["minimum_delta_vs_w4_at_8_every_corpus"]
        and summary["maximum_previous_w4_successes_regressed"] <= gate["maximum_previous_w4_successes_regressed_every_corpus"]
        and summary["minimum_retention_delta_12_minus_8"] >= -gate["maximum_retention_drop_8_to_12_every_corpus"]
        and summary["minimum_causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted_every_corpus"]
        and summary["minimum_primary_only_delta_vs_w4"] >= gate["minimum_primary_only_delta_vs_w4_every_corpus"]
        and summary["pooled_collateral_rescue_fraction"] >= gate["minimum_pooled_collateral_rescue_fraction"]
        and (summary["zero_drive_exact_w4"] if gate["zero_drive_exact_w4_every_corpus"] else True)
        and (all(adaptation.values()) if gate["adaptation_every_size"] else True)
    )
    return {
        "schema": "cosmic-organics/w5-confirmation-full-0.1",
        "frozen_from_head": protocol["frozen_from_head"],
        "confirmation_only_no_retuning": True,
        "criteria": gate,
        "rows": rows,
        "summary": summary,
        "passes": passes,
        "scope_boundary": protocol["scope_boundary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(run_confirmation(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
