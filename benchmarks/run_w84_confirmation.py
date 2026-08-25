"""Frozen fresh-seed confirmation for MORPHOS-W8.4 causal-locality handoff."""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.probe_witness_causal_locality import _adaptation
from benchmarks.probe_witness_persistent import _manifest
from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _m2_law,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from benchmarks.run_w4_confirmation import _run
from morphos.witness_causal_locality import CausalLocalityAuthorityGrid2D
from morphos.witness_history_pair import HistoryAwarePairAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w84_confirmation_manifest.json")


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
        raise RuntimeError("W8.4 confirmation corpus produced no binary targets")

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
        "w83_misses": 0,
        "locality_rescues": 0,
        "locality_on_w83_success": 0,
        "locality_events": 0,
        "locality_added": 0,
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
            w83 = _run(
                HistoryAwarePairAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                **kwargs,
            )
            w84 = _run(
                CausalLocalityAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                **kwargs,
            )
            w84_12 = _run(
                CausalLocalityAuthorityGrid2D,
                horizon=protocol["retention_horizon"],
                **kwargs,
            )
            corrupt = _run(
                CausalLocalityAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                corrupt_witness=True,
                **kwargs,
            )
            w83_primary = _run(
                HistoryAwarePairAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                common=False,
                **kwargs,
            )
            w84_primary = _run(
                CausalLocalityAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                common=False,
                **kwargs,
            )
            w83_zero = _run(
                HistoryAwarePairAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                zero_drive=True,
                **kwargs,
            )
            w84_zero = _run(
                CausalLocalityAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                zero_drive=True,
                **kwargs,
            )

            w83_ok = w83.state_string() == target
            w84_ok = w84.state_string() == target
            w84_ok12 = w84_12.state_string() == target
            used_locality = w84_12.locality_pair_decode_events > 0
            rescue = (not w83_ok) and w84_ok12 and used_locality

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
            counts["w83_misses"] += int(not w83_ok)
            counts["locality_rescues"] += int(rescue)
            counts["locality_on_w83_success"] += int(w83_ok and used_locality)
            counts["locality_events"] += w84_12.locality_pair_decode_events
            counts["locality_added"] += w84_12.locality_pair_added_targets

            if rescue:
                rescue_rows.append(
                    {
                        "width": width,
                        "height": height,
                        "seed": spec["seed"],
                        "target_index": target_index,
                        "trial_index": trial_index,
                        "source": source,
                        "w83_exact_at_8": w83_ok,
                        "w84_exact_at_8": w84_ok,
                        "w84_exact_at_12": w84_ok12,
                        "locality_pair_decode_events": w84_12.locality_pair_decode_events,
                        "locality_pair_added_targets": w84_12.locality_pair_added_targets,
                        "last_locality_pair": (
                            list(w84_12.last_locality_pair)
                            if w84_12.last_locality_pair is not None
                            else None
                        ),
                        "last_locality_kind": w84_12.last_locality_kind,
                        "max_repair_set_size": w84_12.max_repair_set_size,
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
            "w83_recovery_at_8": rate("w83_8"),
            "w84_recovery_at_8": rate("w84_8"),
            "w84_recovery_at_12": rate("w84_12"),
            "delta_vs_w83_at_8": rate("w84_8") - rate("w83_8"),
            "previous_w83_successes_regressed": counts["regressed"],
            "fresh_w83_misses": counts["w83_misses"],
            "locality_rescues_of_w83_misses": counts["locality_rescues"],
            "locality_decode_trials_among_w83_successes": counts[
                "locality_on_w83_success"
            ],
            "locality_pair_decode_events": counts["locality_events"],
            "locality_pair_added_targets": counts["locality_added"],
            "causal_drop_when_witness_corrupted": rate("w84_8") - rate("corrupt_8"),
            "primary_only_delta_vs_w83": rate("w84_primary_8") - rate("w83_primary_8"),
            "zero_drive_exact_w83": counts["w84_zero_8"] == counts["w83_zero_8"],
        },
        rescue_rows,
    )


def run_confirmation() -> dict:
    protocol = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    rescues = []
    for spec in protocol["confirmation_corpora"]:
        row, fresh_rescues = _corpus(spec, protocol)
        rows.append(row)
        rescues.extend(fresh_rescues)

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
        "fresh_w83_misses": sum(row["fresh_w83_misses"] for row in rows),
        "locality_rescues_of_w83_misses": sum(
            row["locality_rescues_of_w83_misses"] for row in rows
        ),
        "locality_decode_trials_among_w83_successes": sum(
            row["locality_decode_trials_among_w83_successes"] for row in rows
        ),
        "locality_pair_decode_events": sum(
            row["locality_pair_decode_events"] for row in rows
        ),
        "locality_pair_added_targets": sum(
            row["locality_pair_added_targets"] for row in rows
        ),
        "total_previous_w83_successes_regressed": sum(
            row["previous_w83_successes_regressed"] for row in rows
        ),
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
        all(row["w84_recovery_at_8"] >= gate["minimum_w84_recovery_at_8_every_corpus"] for row in rows)
        and all(row["w84_recovery_at_12"] >= gate["minimum_w84_recovery_at_12_every_corpus"] for row in rows)
        and summary["total_previous_w83_successes_regressed"] <= gate["maximum_previous_w83_successes_regressed"]
        and summary["fresh_w83_misses"] >= gate["minimum_fresh_w83_misses"]
        and summary["locality_rescues_of_w83_misses"] >= gate["minimum_locality_rescues_of_w83_misses"]
        and summary["locality_decode_trials_among_w83_successes"] <= gate["maximum_locality_decode_trials_among_w83_successes"]
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
    summary["passes"] = passes
    return {
        "schema": protocol["schema"],
        "confirmation_only_no_retuning": True,
        "frozen_from_head": protocol["frozen_from_head"],
        "criteria": gate,
        "rows": rows,
        "locality_rescues": rescues,
        "summary": summary,
        "passes": passes,
        "scope_boundary": protocol["scope_boundary"],
    }


def main() -> None:
    report = run_confirmation()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passes"]:
        raise SystemExit("MORPHOS-W8.4 fresh confirmation failed")


if __name__ == "__main__":
    main()
