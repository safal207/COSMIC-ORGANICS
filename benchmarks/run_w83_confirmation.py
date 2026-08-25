"""Frozen fresh-seed confirmation for MORPHOS-W8.3 history-aware pair handoff."""
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
from morphos.witness_executable_margin import ExecutableMarginClosureGrid2D
from morphos.witness_history_pair import HistoryAwarePairAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w83_confirmation_manifest.json")


def _adaptation(config, hierarchy, mirror_law, cells: int, protocol: dict) -> dict:
    model = HistoryAwarePairAuthorityGrid2D(
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
        "history_pair_decode_events": model.history_pair_decode_events,
    }


def _corpus(spec: dict, protocol: dict) -> tuple[dict, list[dict]]:
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
        raise RuntimeError("W8.3 confirmation corpus produced no binary targets")

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
        "w82_misses": 0,
        "history_pair_rescues": 0,
        "history_pair_on_w82_success": 0,
        "history_pair_decode_events": 0,
        "history_pair_added_targets": 0,
    }
    rescue_rows = []

    for target_index, target in enumerate(targets):
        indices = _noise_indices(
            spec["seed"], target_index, cells, protocol["trials_per_target"]
        )
        for trial_index, source in enumerate(indices):
            kwargs = dict(
                target=target,
                indices=[source],
                config=config,
                hierarchy=hierarchy,
                m2_law=mirror_law,
                witness_drive=protocol["witness_drive"],
                witness_commit_delay=protocol["witness_commit_delay"],
            )
            w82 = _run(
                ExecutableMarginClosureGrid2D,
                horizon=protocol["evaluation_horizon"],
                **kwargs,
            )
            w83 = _run(
                HistoryAwarePairAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                **kwargs,
            )
            w83_12 = _run(
                HistoryAwarePairAuthorityGrid2D,
                horizon=protocol["retention_horizon"],
                **kwargs,
            )
            corrupt = _run(
                HistoryAwarePairAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                corrupt_witness=True,
                **kwargs,
            )
            w82_primary = _run(
                ExecutableMarginClosureGrid2D,
                horizon=protocol["evaluation_horizon"],
                common=False,
                **kwargs,
            )
            w83_primary = _run(
                HistoryAwarePairAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                common=False,
                **kwargs,
            )
            w82_zero = _run(
                ExecutableMarginClosureGrid2D,
                horizon=protocol["evaluation_horizon"],
                zero_drive=True,
                **kwargs,
            )
            w83_zero = _run(
                HistoryAwarePairAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                zero_drive=True,
                **kwargs,
            )

            w82_ok = w82.state_string() == target
            w83_ok = w83.state_string() == target
            w83_ok12 = w83_12.state_string() == target
            used_history = w83_12.history_pair_decode_events > 0
            rescue = (not w82_ok) and w83_ok12 and used_history

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
            counts["w82_misses"] += int(not w82_ok)
            counts["history_pair_rescues"] += int(rescue)
            counts["history_pair_on_w82_success"] += int(w82_ok and used_history)
            counts["history_pair_decode_events"] += w83_12.history_pair_decode_events
            counts["history_pair_added_targets"] += w83_12.history_pair_added_targets

            if rescue:
                rescue_rows.append(
                    {
                        "width": width,
                        "height": height,
                        "seed": spec["seed"],
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
    return (
        {
            "width": width,
            "height": height,
            "seed": spec["seed"],
            "trials": n,
            "w82_recovery_at_8": rate("w82_8"),
            "w83_recovery_at_8": rate("w83_8"),
            "w83_recovery_at_12": rate("w83_12"),
            "delta_vs_w82_at_8": rate("w83_8") - rate("w82_8"),
            "previous_w82_successes_regressed": counts["regressed"],
            "fresh_w82_misses": counts["w82_misses"],
            "history_pair_rescues_of_w82_misses": counts["history_pair_rescues"],
            "history_pair_decode_trials_among_w82_successes": counts[
                "history_pair_on_w82_success"
            ],
            "history_pair_decode_events": counts["history_pair_decode_events"],
            "history_pair_added_targets": counts["history_pair_added_targets"],
            "causal_drop_when_witness_corrupted": rate("w83_8") - rate("corrupt_8"),
            "primary_only_delta_vs_w82": rate("w83_primary_8") - rate("w82_primary_8"),
            "zero_drive_exact_w82": counts["w83_zero_8"] == counts["w82_zero_8"],
        },
        rescue_rows,
    )


def run_confirmation() -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    rescue_rows = []
    for spec in protocol["confirmation_corpora"]:
        row, rescues = _corpus(spec, protocol)
        rows.append(row)
        rescue_rows.extend(rescues)

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
    summary = {
        "confirmation_corpora": len(rows),
        "trials": sum(row["trials"] for row in rows),
        "fresh_w82_misses": sum(row["fresh_w82_misses"] for row in rows),
        "history_pair_rescues_of_w82_misses": sum(
            row["history_pair_rescues_of_w82_misses"] for row in rows
        ),
        "history_pair_decode_trials_among_w82_successes": sum(
            row["history_pair_decode_trials_among_w82_successes"] for row in rows
        ),
        "history_pair_decode_events": sum(
            row["history_pair_decode_events"] for row in rows
        ),
        "history_pair_added_targets": sum(
            row["history_pair_added_targets"] for row in rows
        ),
        "total_previous_w82_successes_regressed": sum(
            row["previous_w82_successes_regressed"] for row in rows
        ),
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
        all(row["w83_recovery_at_8"] >= gate["minimum_w83_recovery_at_8_every_corpus"] for row in rows)
        and all(row["w83_recovery_at_12"] >= gate["minimum_w83_recovery_at_12_every_corpus"] for row in rows)
        and summary["total_previous_w82_successes_regressed"] <= gate["maximum_previous_w82_successes_regressed"]
        and summary["fresh_w82_misses"] >= gate["minimum_fresh_w82_misses"]
        and summary["history_pair_rescues_of_w82_misses"] >= gate["minimum_history_pair_rescues_of_w82_misses"]
        and summary["history_pair_decode_trials_among_w82_successes"] <= gate["maximum_history_pair_decode_trials_among_w82_successes"]
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
    summary["passes"] = passes
    return {
        "schema": protocol["schema"],
        "confirmation_only_no_retuning": True,
        "frozen_from_head": protocol["frozen_from_head"],
        "criteria": gate,
        "rows": rows,
        "history_pair_rescues": rescue_rows,
        "summary": summary,
        "passes": passes,
        "scope_boundary": protocol["scope_boundary"],
    }


def main() -> None:
    report = run_confirmation()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passes"]:
        raise SystemExit("MORPHOS-W8.3 fresh confirmation failed")


if __name__ == "__main__":
    main()
