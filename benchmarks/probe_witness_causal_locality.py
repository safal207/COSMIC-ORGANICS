"""Development-only gate for MORPHOS-W8.4 causal-locality handoff."""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.probe_witness_persistent import _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from benchmarks.run_w4_confirmation import _run
from morphos.witness import WitnessLaw
from morphos.witness_causal_locality import CausalLocalityAuthorityGrid2D
from morphos.witness_history_pair import HistoryAwarePairAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w84_causal_locality_manifest.json")


def _adaptation(config, hierarchy, mirror_law, cells: int, spec: dict) -> dict:
    model = CausalLocalityAuthorityGrid2D(
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
        "locality_pair_decode_events": model.locality_pair_decode_events,
    }


def run_probe() -> dict:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    diagnosed = spec["diagnosed_cancellation_residual"]
    rows = []
    diagnosed_rows = []
    adaptation = {}
    totals = {
        "trials": 0,
        "w83_success_8": 0,
        "w84_success_8": 0,
        "w84_success_12": 0,
        "previous_w83_successes_regressed": 0,
        "locality_decode_trials_among_previous_w83_successes": 0,
        "locality_pair_decode_events": 0,
        "locality_pair_added_targets": 0,
        "diagnosed_cancellation_rescued": 0,
        "diagnosed_cancellation_with_locality_decode": 0,
    }

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
            "w83_8": 0,
            "w84_8": 0,
            "w84_12": 0,
            "corrupt_8": 0,
            "w83_primary_8": 0,
            "w84_primary_8": 0,
            "w83_zero_8": 0,
            "w84_zero_8": 0,
            "regressed": 0,
            "locality_on_w83_success": 0,
            "locality_events": 0,
            "locality_added": 0,
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
                w83 = _run(
                    HistoryAwarePairAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w84 = _run(
                    CausalLocalityAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w84_12 = _run(
                    CausalLocalityAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                corrupt = _run(
                    CausalLocalityAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    corrupt_witness=True,
                    **kwargs,
                )
                w83_primary = _run(
                    HistoryAwarePairAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    common=False,
                    **kwargs,
                )
                w84_primary = _run(
                    CausalLocalityAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    common=False,
                    **kwargs,
                )
                w83_zero = _run(
                    HistoryAwarePairAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    zero_drive=True,
                    **kwargs,
                )
                w84_zero = _run(
                    CausalLocalityAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    zero_drive=True,
                    **kwargs,
                )

                w83_ok = w83.state_string() == target
                w84_ok = w84.state_string() == target
                w84_ok12 = w84_12.state_string() == target
                used_locality = w84_12.locality_pair_decode_events > 0

                counts["trials"] += 1
                counts["w83_8"] += int(w83_ok)
                counts["w84_8"] += int(w84_ok)
                counts["w84_12"] += int(w84_ok12)
                counts["corrupt_8"] += int(corrupt.state_string() == target)
                counts["w83_primary_8"] += int(w83_primary.state_string() == target)
                counts["w84_primary_8"] += int(w84_primary.state_string() == target)
                counts["w83_zero_8"] += int(w83_zero.state_string() == target)
                counts["w84_zero_8"] += int(w84_zero.state_string() == target)
                counts["regressed"] += int(w83_ok and not w84_ok)
                counts["locality_on_w83_success"] += int(w83_ok and used_locality)
                counts["locality_events"] += w84_12.locality_pair_decode_events
                counts["locality_added"] += w84_12.locality_pair_added_targets

                if (
                    width == diagnosed["width"]
                    and height == diagnosed["height"]
                    and corpus["seed"] == diagnosed["seed"]
                    and target_index == diagnosed["target_index"]
                    and trial_index == diagnosed["trial_index"]
                    and source == diagnosed["source"]
                ):
                    rescued = w84_ok12
                    pair = (
                        list(w84_12.last_locality_pair)
                        if w84_12.last_locality_pair is not None
                        else None
                    )
                    causal = used_locality and pair == diagnosed["expected_pair"]
                    totals["diagnosed_cancellation_rescued"] += int(rescued)
                    totals["diagnosed_cancellation_with_locality_decode"] += int(causal)
                    diagnosed_rows.append(
                        {
                            "width": width,
                            "height": height,
                            "seed": corpus["seed"],
                            "target_index": target_index,
                            "trial_index": trial_index,
                            "source": source,
                            "w83_exact_at_8": w83_ok,
                            "w84_exact_at_8": w84_ok,
                            "w84_exact_at_12": w84_ok12,
                            "locality_pair_decode_events": w84_12.locality_pair_decode_events,
                            "locality_pair_added_targets": w84_12.locality_pair_added_targets,
                            "last_locality_pair": pair,
                            "last_locality_kind": w84_12.last_locality_kind,
                            "max_repair_set_size": w84_12.max_repair_set_size,
                        }
                    )

        n = counts["trials"]
        rate = lambda key: counts[key] / n
        row = {
            "width": width,
            "height": height,
            "seed": corpus["seed"],
            "trials": n,
            "w83_recovery_at_8": rate("w83_8"),
            "w84_recovery_at_8": rate("w84_8"),
            "w84_recovery_at_12": rate("w84_12"),
            "delta_vs_w83_at_8": rate("w84_8") - rate("w83_8"),
            "previous_w83_successes_regressed": counts["regressed"],
            "locality_decode_trials_among_previous_w83_successes": counts[
                "locality_on_w83_success"
            ],
            "locality_pair_decode_events": counts["locality_events"],
            "locality_pair_added_targets": counts["locality_added"],
            "causal_drop_when_witness_corrupted": rate("w84_8") - rate("corrupt_8"),
            "primary_only_delta_vs_w83": rate("w84_primary_8") - rate("w83_primary_8"),
            "zero_drive_exact_w83": counts["w84_zero_8"] == counts["w83_zero_8"],
        }
        rows.append(row)
        totals["trials"] += n
        totals["w83_success_8"] += counts["w83_8"]
        totals["w84_success_8"] += counts["w84_8"]
        totals["w84_success_12"] += counts["w84_12"]
        totals["previous_w83_successes_regressed"] += counts["regressed"]
        totals["locality_decode_trials_among_previous_w83_successes"] += counts[
            "locality_on_w83_success"
        ]
        totals["locality_pair_decode_events"] += counts["locality_events"]
        totals["locality_pair_added_targets"] += counts["locality_added"]

        size = f"{width}x{height}"
        if size not in adaptation:
            adaptation[size] = _adaptation(
                config, hierarchy, mirror_law, cells, spec
            )

    gate = spec["predeclared_gates"]
    summary = {
        **totals,
        "diagnosed_rows": len(diagnosed_rows),
        "minimum_w84_recovery_at_8": min(row["w84_recovery_at_8"] for row in rows),
        "minimum_w84_recovery_at_12": min(row["w84_recovery_at_12"] for row in rows),
        "minimum_causal_drop_when_witness_corrupted": min(
            row["causal_drop_when_witness_corrupted"] for row in rows
        ),
        "minimum_primary_only_delta_vs_w83": min(
            row["primary_only_delta_vs_w83"] for row in rows
        ),
        "adaptation_by_size": adaptation,
    }

    passes = (
        len(diagnosed_rows) == 1
        and summary["diagnosed_cancellation_rescued"] >= gate["minimum_diagnosed_cancellation_rescued"]
        and summary["diagnosed_cancellation_with_locality_decode"] >= gate["minimum_diagnosed_cancellation_with_locality_decode"]
        and all(row["w84_recovery_at_8"] >= gate["minimum_w84_recovery_at_8_every_corpus"] for row in rows)
        and all(row["w84_recovery_at_12"] >= gate["minimum_w84_recovery_at_12_every_corpus"] for row in rows)
        and summary["previous_w83_successes_regressed"] <= gate["maximum_previous_w83_successes_regressed"]
        and summary["locality_decode_trials_among_previous_w83_successes"] <= gate["maximum_locality_decode_trials_among_previous_w83_successes"]
        and all(row["causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted_every_corpus"] for row in rows)
        and all(row["primary_only_delta_vs_w83"] >= gate["minimum_primary_only_delta_vs_w83_every_corpus"] for row in rows)
        and all(row["zero_drive_exact_w83"] == gate["zero_drive_exact_w83_every_corpus"] for row in rows)
        and (
            all(
                item["passes"]
                and item["completion_events"] == gate["adaptation_completion_events"]
                and item["executable_closure_events"] == gate["adaptation_executable_closure_events"]
                and item["history_pair_decode_events"] == gate["adaptation_history_pair_decode_events"]
                and item["locality_pair_decode_events"] == gate["adaptation_locality_pair_decode_events"]
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
        "diagnosed_cancellation": diagnosed_rows,
        "summary": summary,
        "passes": passes,
        "scope_boundary": spec["scope_boundary"],
    }


def main() -> None:
    report = run_probe()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passes"]:
        raise SystemExit("MORPHOS-W8.4 development gate failed")


if __name__ == "__main__":
    main()
