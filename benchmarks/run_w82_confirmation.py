"""Frozen fresh-seed confirmation for MORPHOS-W8.2 executable margin closure."""
from __future__ import annotations

import json
from pathlib import Path

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
from morphos.witness_executable_margin import ExecutableMarginClosureGrid2D
from morphos.witness_path_completion import PathCompletionAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w82_confirmation_manifest.json")


def _adaptation(config, hierarchy, mirror_law, cells: int, protocol: dict) -> dict:
    model = ExecutableMarginClosureGrid2D(
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
    return {
        "passes": (
            model.state_string() == expected
            and model.local_mirror_string() == expected
            and model.domain_mirror_string() == expected
            and model.system_mirror_string() == expected
            and model.witness_signature() != initial
        ),
        "completion_events": model.margin_completion_events,
        "executable_closure_events": model.executable_closure_events,
    }


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
        raise RuntimeError("W8.2 confirmation corpus produced no binary targets")

    counts = {
        "trials": 0,
        "w81_common_8": 0,
        "w82_common_8": 0,
        "w82_common_12": 0,
        "w82_corrupt_8": 0,
        "w81_primary_8": 0,
        "w82_primary_8": 0,
        "w81_zero_8": 0,
        "w82_zero_8": 0,
        "w81_success_regressed": 0,
        "closure_events": 0,
        "closure_steps": 0,
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
            w81 = _run(
                PathCompletionAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                **kwargs,
            )
            w82 = _run(
                ExecutableMarginClosureGrid2D,
                horizon=protocol["evaluation_horizon"],
                **kwargs,
            )
            w82_12 = _run(
                ExecutableMarginClosureGrid2D,
                horizon=protocol["retention_horizon"],
                **kwargs,
            )
            corrupt = _run(
                ExecutableMarginClosureGrid2D,
                horizon=protocol["evaluation_horizon"],
                corrupt_witness=True,
                **kwargs,
            )
            w81_primary = _run(
                PathCompletionAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                common=False,
                **kwargs,
            )
            w82_primary = _run(
                ExecutableMarginClosureGrid2D,
                horizon=protocol["evaluation_horizon"],
                common=False,
                **kwargs,
            )
            w81_zero = _run(
                PathCompletionAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                zero_drive=True,
                **kwargs,
            )
            w82_zero = _run(
                ExecutableMarginClosureGrid2D,
                horizon=protocol["evaluation_horizon"],
                zero_drive=True,
                **kwargs,
            )

            w81_ok = w81.state_string() == target
            w82_ok = w82.state_string() == target
            counts["trials"] += 1
            counts["w81_common_8"] += int(w81_ok)
            counts["w82_common_8"] += int(w82_ok)
            counts["w82_common_12"] += int(w82_12.state_string() == target)
            counts["w82_corrupt_8"] += int(corrupt.state_string() == target)
            counts["w81_primary_8"] += int(w81_primary.state_string() == target)
            counts["w82_primary_8"] += int(w82_primary.state_string() == target)
            counts["w81_zero_8"] += int(w81_zero.state_string() == target)
            counts["w82_zero_8"] += int(w82_zero.state_string() == target)
            counts["w81_success_regressed"] += int(w81_ok and not w82_ok)
            counts["closure_events"] += w82.executable_closure_events
            counts["closure_steps"] += w82.executable_closure_steps

    n = counts["trials"]
    rate = lambda key: counts[key] / n
    return {
        "width": width,
        "height": height,
        "seed": spec["seed"],
        "trials": n,
        "w81_recovery_at_8": rate("w81_common_8"),
        "w82_recovery_at_8": rate("w82_common_8"),
        "w82_recovery_at_12": rate("w82_common_12"),
        "delta_vs_w81_at_8": rate("w82_common_8") - rate("w81_common_8"),
        "previous_w81_successes_regressed": counts["w81_success_regressed"],
        "causal_drop_when_witness_corrupted": rate("w82_common_8") - rate("w82_corrupt_8"),
        "primary_only_delta_vs_w81": rate("w82_primary_8") - rate("w81_primary_8"),
        "zero_drive_exact_w81": counts["w82_zero_8"] == counts["w81_zero_8"],
        "executable_closure_events": counts["closure_events"],
        "executable_closure_steps": counts["closure_steps"],
    }


def run_confirmation() -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = [_corpus(spec, protocol) for spec in protocol["confirmation_corpora"]]
    base = _manifest()
    adaptation = {}
    for spec in protocol["confirmation_corpora"]:
        size = f"{spec['width']}x{spec['height']}"
        if size in adaptation:
            continue
        config, hierarchy = _s2_components(base, spec["width"], spec["height"])
        adaptation[size] = _adaptation(
            config,
            hierarchy,
            _m2_law(base),
            spec["width"] * spec["height"],
            protocol,
        )

    gate = protocol["predeclared_gates"]
    passes = (
        all(row["w82_recovery_at_8"] >= gate["minimum_w82_recovery_at_8_every_corpus"] for row in rows)
        and all(row["w82_recovery_at_12"] >= gate["minimum_w82_recovery_at_12_every_corpus"] for row in rows)
        and all(row["previous_w81_successes_regressed"] <= gate["maximum_previous_w81_successes_regressed_every_corpus"] for row in rows)
        and all(row["causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted_every_corpus"] for row in rows)
        and all(row["primary_only_delta_vs_w81"] >= gate["minimum_primary_only_delta_vs_w81_every_corpus"] for row in rows)
        and all(row["zero_drive_exact_w81"] == gate["zero_drive_exact_w81_every_corpus"] for row in rows)
        and (
            all(
                item["passes"]
                and item["completion_events"] == gate["adaptation_completion_events"]
                and item["executable_closure_events"] == gate["adaptation_executable_closure_events"]
                for item in adaptation.values()
            )
            if gate["adaptation_every_size"]
            else True
        )
    )

    summary = {
        "confirmation_corpora": len(rows),
        "trials": sum(row["trials"] for row in rows),
        "minimum_w82_recovery_at_8": min(row["w82_recovery_at_8"] for row in rows),
        "minimum_w82_recovery_at_12": min(row["w82_recovery_at_12"] for row in rows),
        "minimum_causal_drop_when_witness_corrupted": min(row["causal_drop_when_witness_corrupted"] for row in rows),
        "minimum_primary_only_delta_vs_w81": min(row["primary_only_delta_vs_w81"] for row in rows),
        "total_previous_w81_successes_regressed": sum(row["previous_w81_successes_regressed"] for row in rows),
        "total_executable_closure_events": sum(row["executable_closure_events"] for row in rows),
        "total_executable_closure_steps": sum(row["executable_closure_steps"] for row in rows),
        "adaptation_by_size": adaptation,
        "passes": passes,
    }
    return {
        "schema": protocol["schema"],
        "confirmation_only_no_retuning": True,
        "frozen_from_head": protocol["frozen_from_head"],
        "criteria": gate,
        "rows": rows,
        "summary": summary,
        "passes": passes,
        "scope_boundary": protocol["scope_boundary"],
    }


def main() -> None:
    report = run_confirmation()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passes"]:
        raise SystemExit("MORPHOS-W8.2 fresh confirmation failed")


if __name__ == "__main__":
    main()
