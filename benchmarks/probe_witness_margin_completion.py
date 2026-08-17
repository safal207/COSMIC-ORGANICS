"""Development-only gate for MORPHOS-W8 entry margin completion.

The corpus is intentionally the already-diagnosed W7 confirmation set. It is
training/development evidence, not independent confirmation. W8 is frozen only
if it rescues the diagnosed source-threshold boundary without regressing W7's
already successful trials or bypassing witness causality/adaptation semantics.
"""
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
from morphos.witness_margin_completion import MarginCompletionAuthorityGrid2D
from morphos.witness_repair_set import RepairSetAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w8_margin_completion_manifest.json")


def _adaptation(config, hierarchy, mirror_law, cells: int, spec: dict) -> tuple[bool, int]:
    model = MarginCompletionAuthorityGrid2D(
        "A" * cells,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
        witness_law=WitnessLaw(
            witness_drive=spec["witness_drive"],
            commit_delay=spec["witness_commit_delay"],
        ),
    )
    initial = model.witness_signature()
    model.run([2.0] * 18)
    model.run([0.0] * 16)
    expected = "C" * cells
    ok = (
        model.state_string() == expected
        and model.local_mirror_string() == expected
        and model.domain_mirror_string() == expected
        and model.system_mirror_string() == expected
        and model.witness_signature() != initial
    )
    return ok, model.margin_completion_events


def run_probe() -> dict:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    rows = []
    residual_rows = []
    totals = {
        "trials": 0,
        "w7_success_8": 0,
        "w8_success_8": 0,
        "w8_success_12": 0,
        "previous_w7_successes_regressed": 0,
        "completion_trials_on_previous_w7_successes": 0,
        "source_endpoints_rescued": 0,
        "exact_persistent_failures_rescued": 0,
    }
    adaptation_by_size = {}

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
        counts = {
            "trials": 0,
            "w7_8": 0,
            "w7_12": 0,
            "w8_8": 0,
            "w8_12": 0,
            "corrupt_8": 0,
            "regressed": 0,
            "completion_on_w7_success": 0,
        }

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
                w7_8 = _run(
                    RepairSetAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w7_12 = _run(
                    RepairSetAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                w8_8 = _run(
                    MarginCompletionAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w8_12 = _run(
                    MarginCompletionAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                corrupt = _run(
                    MarginCompletionAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    corrupt_witness=True,
                    **kwargs,
                )

                w7_ok8 = w7_8.state_string() == target
                w7_ok12 = w7_12.state_string() == target
                w8_ok8 = w8_8.state_string() == target
                w8_ok12 = w8_12.state_string() == target
                corrupt_ok = corrupt.state_string() == target

                counts["trials"] += 1
                counts["w7_8"] += int(w7_ok8)
                counts["w7_12"] += int(w7_ok12)
                counts["w8_8"] += int(w8_ok8)
                counts["w8_12"] += int(w8_ok12)
                counts["corrupt_8"] += int(corrupt_ok)
                counts["regressed"] += int(w7_ok8 and not w8_ok8)
                counts["completion_on_w7_success"] += int(
                    w7_ok8 and w8_8.margin_completion_events > 0
                )

                if not w7_ok12:
                    source_rescued = w8_12.states[source] == target[source]
                    exact_rescued = w8_ok12
                    totals["source_endpoints_rescued"] += int(source_rescued)
                    totals["exact_persistent_failures_rescued"] += int(exact_rescued)
                    residual_rows.append(
                        {
                            "width": width,
                            "height": height,
                            "seed": corpus["seed"],
                            "target_index": target_index,
                            "trial_index": trial_index,
                            "source": source,
                            "source_rescued_at_12": source_rescued,
                            "exact_recovered_at_8": w8_ok8,
                            "exact_recovered_at_12": exact_rescued,
                            "completion_events_at_8": w8_8.margin_completion_events,
                            "completion_total_at_8": w8_8.margin_completion_total,
                            "completion_max_at_8": w8_8.margin_completion_max,
                            "anchor_completion_events_at_8": w8_8.margin_completion_anchor_events,
                            "adaptive_completion_events_at_8": w8_8.margin_completion_adaptive_events,
                            "handoff_history_at_12": [list(pair) for pair in w8_12.handoff_history],
                            "max_repair_set_size_at_12": w8_12.max_repair_set_size,
                        }
                    )

        n = counts["trials"]
        rate = lambda key: counts[key] / n
        rows.append(
            {
                "width": width,
                "height": height,
                "seed": corpus["seed"],
                "trials": n,
                "w7_recovery_at_8": rate("w7_8"),
                "w7_recovery_at_12": rate("w7_12"),
                "w8_recovery_at_8": rate("w8_8"),
                "w8_recovery_at_12": rate("w8_12"),
                "delta_vs_w7_at_8": rate("w8_8") - rate("w7_8"),
                "previous_w7_successes_regressed": counts["regressed"],
                "completion_trials_on_previous_w7_successes": counts["completion_on_w7_success"],
                "causal_drop_when_witness_corrupted": rate("w8_8") - rate("corrupt_8"),
            }
        )
        totals["trials"] += n
        totals["w7_success_8"] += counts["w7_8"]
        totals["w8_success_8"] += counts["w8_8"]
        totals["w8_success_12"] += counts["w8_12"]
        totals["previous_w7_successes_regressed"] += counts["regressed"]
        totals["completion_trials_on_previous_w7_successes"] += counts[
            "completion_on_w7_success"
        ]

        size = f"{width}x{height}"
        if size not in adaptation_by_size:
            ok, events = _adaptation(config, hierarchy, mirror_law, cells, spec)
            adaptation_by_size[size] = {
                "passes": ok,
                "margin_completion_events": events,
            }

    # Zero witness means no independent authority can open the repair fence;
    # therefore W8 completion must remain unreachable.
    zero_completion_events = 0
    for corpus in spec["corpora"]:
        width, height = corpus["width"], corpus["height"]
        cells = width * height
        config, hierarchy = _s2_components(base, width, height)
        mirror_law = _m2_law(base)
        target = _fixed_binary_targets(
            _sha_binary_seeds(corpus["seed"], corpus["samples"], cells),
            config,
            hierarchy,
            spec["target_discovery_steps"],
        )[0]
        source = _noise_indices(corpus["seed"], 0, cells, spec["trials_per_target"])[0]
        model = MarginCompletionAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=mirror_law,
            witness_law=WitnessLaw(witness_drive=0.0, commit_delay=spec["witness_commit_delay"]),
        )
        _corrupt_all(model, source)
        model.run([0.0] * spec["evaluation_horizon"])
        zero_completion_events += model.margin_completion_events

    summary = {
        **totals,
        "diagnosed_w7_persistent_failures": len(residual_rows),
        "overall_w7_recovery_at_8": totals["w7_success_8"] / totals["trials"],
        "overall_w8_recovery_at_8": totals["w8_success_8"] / totals["trials"],
        "overall_w8_recovery_at_12": totals["w8_success_12"] / totals["trials"],
        "minimum_w8_recovery_at_8": min(row["w8_recovery_at_8"] for row in rows),
        "minimum_w8_recovery_at_12": min(row["w8_recovery_at_12"] for row in rows),
        "minimum_causal_drop_when_witness_corrupted": min(
            row["causal_drop_when_witness_corrupted"] for row in rows
        ),
        "zero_witness_completion_events": zero_completion_events,
        "adaptation_by_size": adaptation_by_size,
        "maximum_completion": max(
            (row["completion_max_at_8"] for row in residual_rows), default=0.0
        ),
        "mean_completion": (
            sum(row["completion_total_at_8"] for row in residual_rows) / len(residual_rows)
            if residual_rows else 0.0
        ),
    }

    gate = spec["predeclared_gates"]
    passes = (
        len(residual_rows) == spec["diagnosed_w7_persistent_failures"]
        and summary["source_endpoints_rescued"] >= gate["minimum_source_endpoints_rescued"]
        and summary["exact_persistent_failures_rescued"] >= gate["minimum_exact_persistent_failures_rescued"]
        and summary["previous_w7_successes_regressed"] <= gate["maximum_previous_w7_successes_regressed"]
        and summary["completion_trials_on_previous_w7_successes"] <= gate["maximum_completion_trials_among_previous_w7_successes"]
        and summary["minimum_w8_recovery_at_8"] >= gate["minimum_recovery_at_8_every_corpus"]
        and summary["minimum_w8_recovery_at_12"] >= gate["minimum_recovery_at_12_every_corpus"]
        and summary["minimum_causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted_every_corpus"]
        and summary["zero_witness_completion_events"] == gate["zero_witness_completion_events"]
        and all(
            row["passes"]
            and row["margin_completion_events"] == gate["adaptation_completion_events"]
            for row in adaptation_by_size.values()
        )
    )

    return {
        "schema": spec["schema"],
        "development_only": True,
        "independent_confirmation": False,
        "retunes_w7": False,
        "criteria": gate,
        "rows": rows,
        "residual_cases": residual_rows,
        "summary": summary,
        "passes": passes,
        "scope_boundary": spec["scope_boundary"],
    }


def main() -> None:
    report = run_probe()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passes"]:
        raise SystemExit("MORPHOS-W8 development gate failed")


if __name__ == "__main__":
    main()
