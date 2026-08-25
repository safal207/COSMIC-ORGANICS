"""Development-only gate for MORPHOS-W8.5 transition-state GF(2) handoff."""
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
from morphos.witness_multierasure import MultiErasureAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w85_multierasure_manifest.json")


def _adaptation(config, hierarchy, mirror_law, cells: int, spec: dict) -> dict:
    model = MultiErasureAuthorityGrid2D(
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
        "multi_erasure_decode_events": model.multi_erasure_decode_events,
    }


def run_probe() -> dict:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    diagnosed = {
        (row["width"], row["height"], row["seed"], row["target_index"], row["trial_index"], row["source"]): row["class"]
        for row in spec["diagnosed_tick8_misses"]
    }

    rows = []
    diagnosed_rows = []
    adaptation = {}
    totals = {
        "trials": 0,
        "w84_success_8": 0,
        "w85_success_8": 0,
        "w85_success_12": 0,
        "previous_w84_successes_regressed": 0,
        "multi_erasure_decode_events": 0,
        "multi_erasure_added_targets": 0,
        "multi_erasure_decode_trials": 0,
        "multi_erasure_decode_trials_among_w84_successes": 0,
        "diagnosed_tick8_misses_rescued": 0,
        "diagnosed_misses_with_multi_erasure_decode": 0,
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
            "w84_8": 0,
            "w85_8": 0,
            "w85_12": 0,
            "corrupt_8": 0,
            "w84_primary_8": 0,
            "w85_primary_8": 0,
            "w84_zero_8": 0,
            "w85_zero_8": 0,
            "regressed": 0,
            "decode_events": 0,
            "added_targets": 0,
            "decode_trials": 0,
            "decode_on_w84_success": 0,
        }

        for target_index, target in enumerate(targets):
            sources = _noise_indices(
                corpus["seed"], target_index, cells, spec["trials_per_target"]
            )
            for trial_index, source in enumerate(sources):
                kwargs = dict(
                    target=target,
                    indices=[source],
                    config=config,
                    hierarchy=hierarchy,
                    m2_law=mirror_law,
                    witness_drive=spec["witness_drive"],
                    witness_commit_delay=spec["witness_commit_delay"],
                )
                w84 = _run(
                    CausalLocalityAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w85 = _run(
                    MultiErasureAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w85_12 = _run(
                    MultiErasureAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                corrupt = _run(
                    MultiErasureAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    corrupt_witness=True,
                    **kwargs,
                )
                w84_primary = _run(
                    CausalLocalityAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    common=False,
                    **kwargs,
                )
                w85_primary = _run(
                    MultiErasureAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    common=False,
                    **kwargs,
                )
                w84_zero = _run(
                    CausalLocalityAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    zero_drive=True,
                    **kwargs,
                )
                w85_zero = _run(
                    MultiErasureAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    zero_drive=True,
                    **kwargs,
                )

                w84_ok = w84.state_string() == target
                w85_ok = w85.state_string() == target
                w85_ok12 = w85_12.state_string() == target
                used = w85_12.multi_erasure_decode_events > 0

                counts["trials"] += 1
                counts["w84_8"] += int(w84_ok)
                counts["w85_8"] += int(w85_ok)
                counts["w85_12"] += int(w85_ok12)
                counts["corrupt_8"] += int(corrupt.state_string() == target)
                counts["w84_primary_8"] += int(w84_primary.state_string() == target)
                counts["w85_primary_8"] += int(w85_primary.state_string() == target)
                counts["w84_zero_8"] += int(w84_zero.state_string() == target)
                counts["w85_zero_8"] += int(w85_zero.state_string() == target)
                counts["regressed"] += int(w84_ok and not w85_ok)
                counts["decode_events"] += w85_12.multi_erasure_decode_events
                counts["added_targets"] += w85_12.multi_erasure_added_targets
                counts["decode_trials"] += int(used)
                counts["decode_on_w84_success"] += int(w84_ok and used)

                key = (width, height, corpus["seed"], target_index, trial_index, source)
                if key in diagnosed:
                    rescued = (not w84_ok) and w85_ok and w85_ok12
                    causal = rescued and used
                    totals["diagnosed_tick8_misses_rescued"] += int(rescued)
                    totals["diagnosed_misses_with_multi_erasure_decode"] += int(causal)
                    diagnosed_rows.append(
                        {
                            "width": width,
                            "height": height,
                            "seed": corpus["seed"],
                            "target_index": target_index,
                            "trial_index": trial_index,
                            "source": source,
                            "class": diagnosed[key],
                            "w84_exact_at_8": w84_ok,
                            "w85_exact_at_8": w85_ok,
                            "w85_exact_at_12": w85_ok12,
                            "multi_erasure_decode_events": w85_12.multi_erasure_decode_events,
                            "multi_erasure_added_targets": w85_12.multi_erasure_added_targets,
                            "last_multi_erasure_indices": (
                                list(w85_12.last_multi_erasure_indices)
                                if w85_12.last_multi_erasure_indices is not None
                                else None
                            ),
                            "last_multi_erasure_targets": (
                                list(w85_12.last_multi_erasure_targets)
                                if w85_12.last_multi_erasure_targets is not None
                                else None
                            ),
                            "max_repair_set_size": w85_12.max_repair_set_size,
                        }
                    )

        n = counts["trials"]
        rate = lambda key: counts[key] / n
        row = {
            "width": width,
            "height": height,
            "seed": corpus["seed"],
            "trials": n,
            "w84_recovery_at_8": rate("w84_8"),
            "w85_recovery_at_8": rate("w85_8"),
            "w85_recovery_at_12": rate("w85_12"),
            "delta_vs_w84_at_8": rate("w85_8") - rate("w84_8"),
            "previous_w84_successes_regressed": counts["regressed"],
            "multi_erasure_decode_events": counts["decode_events"],
            "multi_erasure_added_targets": counts["added_targets"],
            "multi_erasure_decode_trials": counts["decode_trials"],
            "multi_erasure_decode_trials_among_w84_successes": counts[
                "decode_on_w84_success"
            ],
            "causal_drop_when_witness_corrupted": rate("w85_8") - rate("corrupt_8"),
            "primary_only_delta_vs_w84": rate("w85_primary_8") - rate("w84_primary_8"),
            "zero_drive_exact_w84": counts["w85_zero_8"] == counts["w84_zero_8"],
        }
        rows.append(row)

        totals["trials"] += n
        totals["w84_success_8"] += counts["w84_8"]
        totals["w85_success_8"] += counts["w85_8"]
        totals["w85_success_12"] += counts["w85_12"]
        totals["previous_w84_successes_regressed"] += counts["regressed"]
        totals["multi_erasure_decode_events"] += counts["decode_events"]
        totals["multi_erasure_added_targets"] += counts["added_targets"]
        totals["multi_erasure_decode_trials"] += counts["decode_trials"]
        totals["multi_erasure_decode_trials_among_w84_successes"] += counts[
            "decode_on_w84_success"
        ]

        size = f"{width}x{height}"
        if size not in adaptation:
            adaptation[size] = _adaptation(
                config, hierarchy, mirror_law, cells, spec
            )

    gate = spec["predeclared_gates"]
    summary = {
        **totals,
        "diagnosed_rows": len(diagnosed_rows),
        "minimum_w85_recovery_at_8": min(row["w85_recovery_at_8"] for row in rows),
        "minimum_w85_recovery_at_12": min(row["w85_recovery_at_12"] for row in rows),
        "minimum_causal_drop_when_witness_corrupted": min(
            row["causal_drop_when_witness_corrupted"] for row in rows
        ),
        "minimum_primary_only_delta_vs_w84": min(
            row["primary_only_delta_vs_w84"] for row in rows
        ),
        "adaptation_by_size": adaptation,
    }

    passes = (
        len(diagnosed_rows) == len(spec["diagnosed_tick8_misses"])
        and summary["diagnosed_tick8_misses_rescued"] >= gate["minimum_diagnosed_tick8_misses_rescued"]
        and summary["diagnosed_misses_with_multi_erasure_decode"] >= gate["minimum_diagnosed_misses_with_multi_erasure_decode"]
        and all(row["w85_recovery_at_8"] >= gate["minimum_w85_recovery_at_8_every_corpus"] for row in rows)
        and all(row["w85_recovery_at_12"] >= gate["minimum_w85_recovery_at_12_every_corpus"] for row in rows)
        and summary["previous_w84_successes_regressed"] <= gate["maximum_previous_w84_successes_regressed"]
        and all(row["causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted_every_corpus"] for row in rows)
        and all(row["primary_only_delta_vs_w84"] >= gate["minimum_primary_only_delta_vs_w84_every_corpus"] for row in rows)
        and all(row["zero_drive_exact_w84"] == gate["zero_drive_exact_w84_every_corpus"] for row in rows)
        and (
            all(
                item["passes"]
                and item["completion_events"] == gate["adaptation_completion_events"]
                and item["executable_closure_events"] == gate["adaptation_executable_closure_events"]
                and item["history_pair_decode_events"] == gate["adaptation_history_pair_decode_events"]
                and item["locality_pair_decode_events"] == gate["adaptation_locality_pair_decode_events"]
                and item["multi_erasure_decode_events"] == gate["adaptation_multi_erasure_decode_events"]
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
        "diagnosed_tick8_misses": diagnosed_rows,
        "summary": summary,
        "passes": passes,
        "scope_boundary": spec["scope_boundary"],
    }


def main() -> None:
    report = run_probe()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passes"]:
        raise SystemExit("MORPHOS-W8.5 development gate failed")


if __name__ == "__main__":
    main()
