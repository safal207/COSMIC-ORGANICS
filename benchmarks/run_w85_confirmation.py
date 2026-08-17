"""Frozen fresh-seed confirmation for MORPHOS-W8.5 multi-M GF(2) handoff."""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.probe_witness_multierasure import _adaptation
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
from morphos.witness_multierasure import MultiErasureAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w85_confirmation_manifest.json")


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
        raise RuntimeError("W8.5 confirmation corpus produced no binary targets")

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
        "w84_misses": 0,
        "multi_erasure_rescues": 0,
        "decode_trials": 0,
        "decode_on_w84_success": 0,
        "decode_events": 0,
        "added_targets": 0,
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
            w84 = _run(
                CausalLocalityAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                **kwargs,
            )
            w85 = _run(
                MultiErasureAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                **kwargs,
            )
            w85_12 = _run(
                MultiErasureAuthorityGrid2D,
                horizon=protocol["retention_horizon"],
                **kwargs,
            )
            corrupt = _run(
                MultiErasureAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                corrupt_witness=True,
                **kwargs,
            )
            w84_primary = _run(
                CausalLocalityAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                common=False,
                **kwargs,
            )
            w85_primary = _run(
                MultiErasureAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                common=False,
                **kwargs,
            )
            w84_zero = _run(
                CausalLocalityAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                zero_drive=True,
                **kwargs,
            )
            w85_zero = _run(
                MultiErasureAuthorityGrid2D,
                horizon=protocol["evaluation_horizon"],
                zero_drive=True,
                **kwargs,
            )

            w84_ok = w84.state_string() == target
            w85_ok = w85.state_string() == target
            w85_ok12 = w85_12.state_string() == target
            used = w85_12.multi_erasure_decode_events > 0
            rescue = (not w84_ok) and w85_ok and w85_ok12 and used

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
            counts["w84_misses"] += int(not w84_ok)
            counts["multi_erasure_rescues"] += int(rescue)
            counts["decode_trials"] += int(used)
            counts["decode_on_w84_success"] += int(w84_ok and used)
            counts["decode_events"] += w85_12.multi_erasure_decode_events
            counts["added_targets"] += w85_12.multi_erasure_added_targets

            if rescue:
                rescue_rows.append(
                    {
                        "width": width,
                        "height": height,
                        "seed": spec["seed"],
                        "target_index": target_index,
                        "trial_index": trial_index,
                        "source": source,
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
    return (
        {
            "width": width,
            "height": height,
            "seed": spec["seed"],
            "trials": n,
            "w84_recovery_at_8": rate("w84_8"),
            "w85_recovery_at_8": rate("w85_8"),
            "w85_recovery_at_12": rate("w85_12"),
            "delta_vs_w84_at_8": rate("w85_8") - rate("w84_8"),
            "previous_w84_successes_regressed": counts["regressed"],
            "fresh_w84_misses": counts["w84_misses"],
            "multi_erasure_rescues_of_w84_misses": counts["multi_erasure_rescues"],
            "multi_erasure_decode_trials": counts["decode_trials"],
            "multi_erasure_decode_trials_among_w84_successes": counts[
                "decode_on_w84_success"
            ],
            "multi_erasure_decode_events": counts["decode_events"],
            "multi_erasure_added_targets": counts["added_targets"],
            "causal_drop_when_witness_corrupted": rate("w85_8") - rate("corrupt_8"),
            "primary_only_delta_vs_w84": rate("w85_primary_8") - rate("w84_primary_8"),
            "zero_drive_exact_w84": counts["w85_zero_8"] == counts["w84_zero_8"],
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
        "fresh_w84_misses": sum(row["fresh_w84_misses"] for row in rows),
        "multi_erasure_rescues_of_w84_misses": sum(
            row["multi_erasure_rescues_of_w84_misses"] for row in rows
        ),
        "multi_erasure_decode_trials": sum(
            row["multi_erasure_decode_trials"] for row in rows
        ),
        "multi_erasure_decode_trials_among_w84_successes": sum(
            row["multi_erasure_decode_trials_among_w84_successes"] for row in rows
        ),
        "multi_erasure_decode_events": sum(
            row["multi_erasure_decode_events"] for row in rows
        ),
        "multi_erasure_added_targets": sum(
            row["multi_erasure_added_targets"] for row in rows
        ),
        "total_previous_w84_successes_regressed": sum(
            row["previous_w84_successes_regressed"] for row in rows
        ),
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
        all(row["w85_recovery_at_8"] >= gate["minimum_w85_recovery_at_8_every_corpus"] for row in rows)
        and all(row["w85_recovery_at_12"] >= gate["minimum_w85_recovery_at_12_every_corpus"] for row in rows)
        and summary["total_previous_w84_successes_regressed"] <= gate["maximum_previous_w84_successes_regressed"]
        and summary["fresh_w84_misses"] >= gate["minimum_fresh_w84_misses"]
        and summary["multi_erasure_rescues_of_w84_misses"] >= gate["minimum_multi_erasure_rescues_of_w84_misses"]
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
    summary["passes"] = passes
    return {
        "schema": protocol["schema"],
        "confirmation_only_no_retuning": True,
        "frozen_from_head": protocol["frozen_from_head"],
        "criteria": gate,
        "rows": rows,
        "multi_erasure_rescues": rescues,
        "summary": summary,
        "passes": passes,
        "scope_boundary": protocol["scope_boundary"],
    }


def main() -> None:
    report = run_confirmation()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passes"]:
        raise SystemExit("MORPHOS-W8.5 fresh confirmation failed")


if __name__ == "__main__":
    main()
