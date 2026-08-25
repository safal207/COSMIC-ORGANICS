"""Frozen independent confirmation for MORPHOS-W7 concurrent repair set."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.probe_witness_persistent import _manifest
from benchmarks.probe_witness_repair_set import _adaptation, _return_handoffs
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from benchmarks.run_w4_confirmation import _run
from morphos.witness_erasure import ErasureAwareAuthorityGrid2D
from morphos.witness_repair_set import RepairSetAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w7_confirmation_manifest.json")


def _protocol() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _corpus(spec: dict, protocol: dict) -> dict:
    base = _manifest()
    width, height = spec["width"], spec["height"]
    cells = width * height
    config, hierarchy = _s2_components(base, width, height)
    mirror_law = _m2_law(base)
    targets = _fixed_binary_targets(
        _sha_binary_seeds(spec["seed"], spec["samples"], cells),
        config,
        hierarchy,
        protocol["target_discovery_steps"],
    )[: protocol["max_targets"]]
    if not targets:
        raise RuntimeError("W7 confirmation corpus produced no binary fixed targets")

    counts = {
        "trials": 0,
        "w6_8": 0,
        "w7_8": 0,
        "w7_12": 0,
        "regressed": 0,
        "corrupt_8": 0,
        "w6_primary_8": 0,
        "w7_primary_8": 0,
        "w6_zero_8": 0,
        "w7_zero_8": 0,
        "fresh_w6_pingpong_failures": 0,
        "fresh_pingpong_rescued": 0,
        "max_w7_return_handoffs": 0,
    }

    for target_index, target in enumerate(targets):
        indices = _noise_indices(
            spec["seed"], target_index, cells, protocol["trials_per_target"]
        )
        for source in indices:
            kwargs = dict(
                target=target,
                indices=[source],
                config=config,
                hierarchy=hierarchy,
                m2_law=mirror_law,
                witness_drive=protocol["witness_drive"],
                witness_commit_delay=protocol["witness_commit_delay"],
            )
            w6 = _run(
                ErasureAwareAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                **kwargs,
            )
            w7 = _run(
                RepairSetAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                **kwargs,
            )
            w7_12 = _run(
                RepairSetAuthorityGrid2D,
                horizon=protocol["retention_horizon"],
                **kwargs,
            )
            corrupt = _run(
                RepairSetAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                corrupt_witness=True,
                **kwargs,
            )
            w6_primary = _run(
                ErasureAwareAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                common=False,
                **kwargs,
            )
            w7_primary = _run(
                RepairSetAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                common=False,
                **kwargs,
            )
            w6_zero = _run(
                ErasureAwareAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                zero_drive=True,
                **kwargs,
            )
            w7_zero = _run(
                RepairSetAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                zero_drive=True,
                **kwargs,
            )

            w6_ok = w6.state_string() == target
            w7_ok = w7.state_string() == target
            w6_returns = _return_handoffs(w6.handoff_history)
            w7_returns = _return_handoffs(w7.handoff_history)
            pingpong_failure = w6_returns > 0 and not w6_ok

            counts["trials"] += 1
            counts["w6_8"] += int(w6_ok)
            counts["w7_8"] += int(w7_ok)
            counts["w7_12"] += int(w7_12.state_string() == target)
            counts["regressed"] += int(w6_ok and not w7_ok)
            counts["corrupt_8"] += int(corrupt.state_string() == target)
            counts["w6_primary_8"] += int(w6_primary.state_string() == target)
            counts["w7_primary_8"] += int(w7_primary.state_string() == target)
            counts["w6_zero_8"] += int(w6_zero.state_string() == target)
            counts["w7_zero_8"] += int(w7_zero.state_string() == target)
            if pingpong_failure:
                counts["fresh_w6_pingpong_failures"] += 1
                counts["fresh_pingpong_rescued"] += int(w7_ok)
                counts["max_w7_return_handoffs"] = max(
                    counts["max_w7_return_handoffs"], w7_returns
                )

    n = counts["trials"]
    rate = lambda key: counts[key] / n
    return {
        "width": width,
        "height": height,
        "seed": spec["seed"],
        "trials": n,
        "w6_recovery_at_8": rate("w6_8"),
        "w7_recovery_at_8": rate("w7_8"),
        "w7_recovery_at_12": rate("w7_12"),
        "delta_vs_w6_at_8": rate("w7_8") - rate("w6_8"),
        "previous_w6_successes_regressed": counts["regressed"],
        "retention_delta_12_minus_8": rate("w7_12") - rate("w7_8"),
        "causal_drop_when_witness_corrupted": rate("w7_8") - rate("corrupt_8"),
        "primary_only_delta_vs_w6": rate("w7_primary_8") - rate("w6_primary_8"),
        "zero_drive_exact_w6": counts["w7_zero_8"] == counts["w6_zero_8"],
        "fresh_w6_pingpong_failures": counts["fresh_w6_pingpong_failures"],
        "fresh_pingpong_rescued": counts["fresh_pingpong_rescued"],
        "maximum_w7_return_handoffs_on_fresh_pingpong": counts["max_w7_return_handoffs"],
    }


def run_confirmation() -> dict:
    protocol = _protocol()
    rows = [_corpus(spec, protocol) for spec in protocol["confirmation_corpora"]]
    gate = protocol["predeclared_gates"]
    fresh_pingpong = sum(row["fresh_w6_pingpong_failures"] for row in rows)
    rescued = sum(row["fresh_pingpong_rescued"] for row in rows)

    base = _manifest()
    adaptation = {}
    for width, height in sorted({(row["width"], row["height"]) for row in rows}):
        config, hierarchy = _s2_components(base, width, height)
        local_spec = {
            "witness_drive": protocol["witness_drive"],
            "witness_commit_delay": protocol["witness_commit_delay"],
        }
        adaptation[f"{width}x{height}"] = _adaptation(
            config, hierarchy, _m2_law(base), width * height, local_spec
        )

    summary = {
        "minimum_w7_recovery_at_8": min(row["w7_recovery_at_8"] for row in rows),
        "minimum_w7_recovery_at_12": min(row["w7_recovery_at_12"] for row in rows),
        "minimum_delta_vs_w6_at_8": min(row["delta_vs_w6_at_8"] for row in rows),
        "maximum_previous_w6_successes_regressed": max(row["previous_w6_successes_regressed"] for row in rows),
        "minimum_retention_delta_12_minus_8": min(row["retention_delta_12_minus_8"] for row in rows),
        "minimum_causal_drop_when_witness_corrupted": min(row["causal_drop_when_witness_corrupted"] for row in rows),
        "minimum_primary_only_delta_vs_w6": min(row["primary_only_delta_vs_w6"] for row in rows),
        "zero_drive_exact_w6": all(row["zero_drive_exact_w6"] for row in rows),
        "fresh_w6_pingpong_failures": fresh_pingpong,
        "fresh_pingpong_rescued": rescued,
        "pooled_pingpong_rescue_fraction": rescued / fresh_pingpong if fresh_pingpong else 0.0,
        "maximum_w7_return_handoffs_on_fresh_pingpong": max(row["maximum_w7_return_handoffs_on_fresh_pingpong"] for row in rows),
        "adaptation_by_size": adaptation,
    }
    passes = (
        summary["minimum_w7_recovery_at_8"] >= gate["minimum_w7_recovery_at_8_every_corpus"]
        and summary["minimum_w7_recovery_at_12"] >= gate["minimum_w7_recovery_at_12_every_corpus"]
        and summary["minimum_delta_vs_w6_at_8"] >= gate["minimum_delta_vs_w6_at_8_every_corpus"]
        and summary["maximum_previous_w6_successes_regressed"] <= gate["maximum_previous_w6_successes_regressed_every_corpus"]
        and summary["minimum_retention_delta_12_minus_8"] >= -gate["maximum_retention_drop_8_to_12_every_corpus"]
        and summary["minimum_causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted_every_corpus"]
        and summary["minimum_primary_only_delta_vs_w6"] >= gate["minimum_primary_only_delta_vs_w6_every_corpus"]
        and summary["fresh_w6_pingpong_failures"] >= gate["minimum_fresh_w6_pingpong_failures"]
        and summary["pooled_pingpong_rescue_fraction"] >= gate["minimum_pooled_pingpong_rescue_fraction"]
        and summary["maximum_w7_return_handoffs_on_fresh_pingpong"] <= gate["maximum_w7_return_handoffs_on_fresh_pingpong_cases"]
        and (summary["zero_drive_exact_w6"] if gate["zero_drive_exact_w6_every_corpus"] else True)
        and (all(adaptation.values()) if gate["adaptation_every_size"] else True)
    )
    return {
        "schema": "cosmic-organics/w7-confirmation-full-0.1",
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
