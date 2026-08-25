"""Development-only gate for MORPHOS-W8.3 history-aware pair handoff.

The corpus is the already-observed failed W8.2 confirmation set. It is used for
development only; a fresh independent confirmation is mandatory if W8.3 passes.
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
from morphos.witness_executable_margin import ExecutableMarginClosureGrid2D
from morphos.witness_history_pair import HistoryAwarePairAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w83_history_pair_manifest.json")


def _adaptation(config, hierarchy, mirror_law, cells: int, spec: dict) -> dict:
    model = HistoryAwarePairAuthorityGrid2D(
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
        "history_pair_decode_events": model.history_pair_decode_events,
    }


def run_probe() -> dict:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    diagnosed = {
        (row["seed"], row["target_index"], row["trial_index"], row["source"])
        for row in spec["diagnosed_residuals"]
    }
    rows = []
    diagnosed_rows = []
    totals = {
        "trials": 0,
        "w82_success_8": 0,
        "w83_success_8": 0,
        "w83_success_12": 0,
        "previous_w82_successes_regressed": 0,
        "history_pair_decode_trials_among_previous_w82_successes": 0,
        "history_pair_decode_events": 0,
        "history_pair_added_targets": 0,
        "diagnosed_residuals_rescued": 0,
        "diagnosed_residuals_with_history_pair_decode": 0,
    }
    adaptation = {}

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
            "w82_8": 0,
            "w83_8": 0,
            "w83_12": 0,
            "corrupt_8": 0,
            "w82_primary_8": 0,
            "w83_primary_8": 0,
            "w82_zero_8": 0,
            "w83_zero_8": 0,
            "regressed": 0,
            "history_pair_events": 0,
            "history_pair_success_trials": 0,
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
                w82 = _run(
                    ExecutableMarginClosureGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w83 = _run(
                    HistoryAwarePairAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w83_12 = _run(
                    HistoryAwarePairAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                corrupt = _run(
                    HistoryAwarePairAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    corrupt_witness=True,
                    **kwargs,
                )
                w82_primary = _run(
                    ExecutableMarginClosureGrid2D,
                    horizon=spec["evaluation_horizon"],
                    common=False,
                    **kwargs,
                )
                w83_primary = _run(
                    HistoryAwarePairAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    common=False,
                    **kwargs,
                )
                w82_zero = _run(
                    ExecutableMarginClosureGrid2D,
                    horizon=spec["evaluation_horizon"],
                    zero_drive=True,
                    **kwargs,
                )
                w83_zero = _run(
                    HistoryAwarePairAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    zero_drive=True,
                    **kwargs,
                )

                w82_ok = w82.state_string() == target
                w83_ok = w83.state_string() == target
                w83_ok12 = w83_12.state_string() == target
                counts["trials"] += 1
                counts["w82_8"] += int(w82_ok)
                counts["w83_8"] += int(w83_ok)
                counts["w83_12"] += int(w83_ok12)
                counts["corrupt_8"] += int(corrupt.state_string() == target)
                counts["w82_primary_8"] += int(w82_primary.state_string() == target)
                counts["w83_primary_8"] += int(w83_primary.state_string() == target)
                counts["w82_zero_8"] += int(w82_zero.state_string() == target)
                counts["w83_zero_8"] += int(w83_zero.state_string() == target)
                counts["regressed"] += int(w82_ok and not w83_ok)
                counts["history_pair_events"] += w83_12.history_pair_decode_events
                counts["history_pair_success_trials"] += int(
                    w82_ok and w83_12.history_pair_decode_events > 0
                )

                key = (corpus["seed"], target_index, trial_index, source)
                if key in diagnosed:
                    rescued = w83_ok12
                    used = w83_12.history_pair_decode_events > 0
                    totals["diagnosed_residuals_rescued"] += int(rescued)
                    totals["diagnosed_residuals_with_history_pair_decode"] += int(used)
                    diagnosed_rows.append(
                        {
                            "width": width,
                            "height": height,
                            "seed": corpus["seed"],
                            "target_index": target_index,
                            "trial_index": trial_index,
                            "source": source,
                            "w82_exact_at_8": w82_ok,
                            "w83_exact_at_8": w83_ok,
                            "w83_exact_at_12": w83_ok12,
                            "history_pair_decode_events": w83_12.history_pair_decode_events,
                            "history_pair_added_targets": w83_12.history_pair_added_targets,
                            "last_history_pair": (
                                list(w83_12.last_history_pair)
                                if w83_12.last_history_pair is not None
                                else None
                            ),
                            "max_repair_set_size": w83_12.max_repair_set_size,
                        }
                    )

        n = counts["trials"]
        rate = lambda key: counts[key] / n
        row = {
            "width": width,
            "height": height,
            "seed": corpus["seed"],
            "trials": n,
            "w82_recovery_at_8": rate("w82_8"),
            "w83_recovery_at_8": rate("w83_8"),
            "w83_recovery_at_12": rate("w83_12"),
            "delta_vs_w82_at_8": rate("w83_8") - rate("w82_8"),
            "previous_w82_successes_regressed": counts["regressed"],
            "history_pair_decode_trials_among_previous_w82_successes": counts[
                "history_pair_success_trials"
            ],
            "causal_drop_when_witness_corrupted": rate("w83_8") - rate("corrupt_8"),
            "primary_only_delta_vs_w82": rate("w83_primary_8") - rate("w82_primary_8"),
            "zero_drive_exact_w82": counts["w83_zero_8"] == counts["w82_zero_8"],
            "history_pair_decode_events": counts["history_pair_events"],
        }
        rows.append(row)
        totals["trials"] += n
        totals["w82_success_8"] += counts["w82_8"]
        totals["w83_success_8"] += counts["w83_8"]
        totals["w83_success_12"] += counts["w83_12"]
        totals["previous_w82_successes_regressed"] += counts["regressed"]
        totals["history_pair_decode_trials_among_previous_w82_successes"] += counts[
            "history_pair_success_trials"
        ]
        totals["history_pair_decode_events"] += counts["history_pair_events"]

        size = f"{width}x{height}"
        if size not in adaptation:
            adaptation[size] = _adaptation(
                config, hierarchy, mirror_law, cells, spec
            )

    gate = spec["predeclared_gates"]
    summary = {
        **totals,
        "diagnosed_residual_count": len(diagnosed_rows),
        "minimum_w83_recovery_at_8": min(row["w83_recovery_at_8"] for row in rows),
        "minimum_w83_recovery_at_12": min(row["w83_recovery_at_12"] for row in rows),
        "minimum_causal_drop_when_witness_corrupted": min(
            row["causal_drop_when_witness_corrupted"] for row in rows
        ),
        "minimum_primary_only_delta_vs_w82": min(
            row["primary_only_delta_vs_w82"] for row in rows
        ),
        "adaptation_by_size": adaptation,
    }
    passes = (
        len(diagnosed_rows) == len(spec["diagnosed_residuals"])
        and summary["diagnosed_residuals_rescued"] >= gate["minimum_diagnosed_residuals_rescued"]
        and summary["diagnosed_residuals_with_history_pair_decode"] >= gate["minimum_diagnosed_residuals_with_history_pair_decode"]
        and all(row["w83_recovery_at_8"] >= gate["minimum_w83_recovery_at_8_every_corpus"] for row in rows)
        and all(row["w83_recovery_at_12"] >= gate["minimum_w83_recovery_at_12_every_corpus"] for row in rows)
        and summary["previous_w82_successes_regressed"] <= gate["maximum_previous_w82_successes_regressed"]
        and summary["history_pair_decode_trials_among_previous_w82_successes"] <= gate["maximum_history_pair_decode_trials_among_previous_w82_successes"]
        and all(row["causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted_every_corpus"] for row in rows)
        and all(row["primary_only_delta_vs_w82"] >= gate["minimum_primary_only_delta_vs_w82_every_corpus"] for row in rows)
        and all(row["zero_drive_exact_w82"] == gate["zero_drive_exact_w82_every_corpus"] for row in rows)
        and (
            all(
                item["passes"]
                and item["completion_events"] == gate["adaptation_completion_events"]
                and item["executable_closure_events"] == gate["adaptation_executable_closure_events"]
                and item["history_pair_decode_events"] == gate["adaptation_history_pair_decode_events"]
                for item in adaptation.values()
            )
            if gate["adaptation_every_size"]
            else True
        )
    )
    return {
        "schema": spec["schema"],
        "development_only": True,
        "independent_confirmation": False,
        "criteria": gate,
        "rows": rows,
        "diagnosed_residuals": diagnosed_rows,
        "summary": summary,
        "passes": passes,
        "scope_boundary": spec["scope_boundary"],
    }


def main() -> None:
    report = run_probe()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passes"]:
        raise SystemExit("MORPHOS-W8.3 development gate failed")


if __name__ == "__main__":
    main()
