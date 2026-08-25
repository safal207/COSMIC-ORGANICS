"""Development-only gate for MORPHOS-W7 concurrent repair-set control.

W7 is evaluated on the already diagnosed W6 corpus family. It changes no
amplitude or physical-state transition parameter; it keeps active corrective
intent on every touched repair target until transaction-level recommit.
"""
from __future__ import annotations

import json
from pathlib import Path

from benchmarks.probe_witness_erasure import _is_diagnosed_mixed_erasure
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
from morphos.witness_erasure import ErasureAwareAuthorityGrid2D
from morphos.witness_handoff import HandoffAuthorityGrid2D
from morphos.witness_repair_set import RepairSetAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w7_repair_set_manifest.json")


def _return_handoffs(history: list[tuple[int, int]]) -> int:
    if not history:
        return 0
    visited = {history[0][0]}
    returns = 0
    for previous, new in history:
        visited.add(previous)
        if new in visited:
            returns += 1
        visited.add(new)
    return returns


def _adaptation(config, hierarchy, mirror_law, cells: int, spec: dict) -> bool:
    model = RepairSetAuthorityGrid2D(
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
    return (
        model.state_string() == expected
        and model.local_mirror_string() == expected
        and model.domain_mirror_string() == expected
        and model.system_mirror_string() == expected
        and model.witness_signature() != initial
    )


def run_probe() -> dict:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    rows = []
    pingpong_rows = []
    adaptation_by_size: dict[str, bool] = {}

    totals = {
        "trials": 0,
        "w6_success_8": 0,
        "w7_success_8": 0,
        "previous_w6_successes_regressed": 0,
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
            "w6_8": 0,
            "w7_8": 0,
            "w7_12": 0,
            "regressed": 0,
            "corrupt_8": 0,
            "w6_primary_8": 0,
            "w7_primary_8": 0,
            "w6_zero_8": 0,
            "w7_zero_8": 0,
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
                w5_8 = _run(
                    HandoffAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w5_12 = _run(
                    HandoffAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                w6 = _run(
                    ErasureAwareAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w7 = _run(
                    RepairSetAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                w7_12 = _run(
                    RepairSetAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                corrupt = _run(
                    RepairSetAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    corrupt_witness=True,
                    **kwargs,
                )
                w6_primary = _run(
                    ErasureAwareAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    common=False,
                    **kwargs,
                )
                w7_primary = _run(
                    RepairSetAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    common=False,
                    **kwargs,
                )
                w6_zero = _run(
                    ErasureAwareAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    zero_drive=True,
                    **kwargs,
                )
                w7_zero = _run(
                    RepairSetAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    zero_drive=True,
                    **kwargs,
                )

                w6_ok = w6.state_string() == target
                w7_ok = w7.state_string() == target
                pingpong = (
                    _is_diagnosed_mixed_erasure(w5_8, w5_12, target, source)
                    and w6.erasure_handoff_events > 0
                    and _return_handoffs(w6.handoff_history) > 0
                )
                if pingpong:
                    pingpong_rows.append(
                        {
                            "width": width,
                            "height": height,
                            "seed": corpus["seed"],
                            "target_index": target_index,
                            "trial_index": trial_index,
                            "source": source,
                            "w6_return_handoffs": _return_handoffs(w6.handoff_history),
                            "w7_return_handoffs": _return_handoffs(w7.handoff_history),
                            "w7_recovered_at_8": w7_ok,
                            "w7_recovered_at_12": w7_12.state_string() == target,
                            "w7_max_repair_set_size": w7.max_repair_set_size,
                            "w7_repair_set_drive_steps": w7.repair_set_drive_steps,
                            "w7_handoff_history": [list(pair) for pair in w7.handoff_history],
                        }
                    )

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

        n = counts["trials"]
        rate = lambda key: counts[key] / n
        rows.append(
            {
                "width": width,
                "height": height,
                "seed": corpus["seed"],
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
            }
        )
        totals["trials"] += n
        totals["w6_success_8"] += counts["w6_8"]
        totals["w7_success_8"] += counts["w7_8"]
        totals["previous_w6_successes_regressed"] += counts["regressed"]

        size = f"{width}x{height}"
        if size not in adaptation_by_size:
            adaptation_by_size[size] = _adaptation(
                config, hierarchy, mirror_law, cells, spec
            )

    gate = spec["predeclared_gates"]
    summary = {
        "diagnosed_pingpong_cases": len(pingpong_rows),
        "pingpong_cases_recovered_at_8": sum(row["w7_recovered_at_8"] for row in pingpong_rows),
        "pingpong_cases_recovered_at_12": sum(row["w7_recovered_at_12"] for row in pingpong_rows),
        "maximum_post_erasure_return_handoffs_per_pingpong_case": max(
            (row["w7_return_handoffs"] for row in pingpong_rows), default=0
        ),
        "minimum_repair_set_size_on_pingpong_cases": min(
            (row["w7_max_repair_set_size"] for row in pingpong_rows), default=0
        ),
        "previous_w6_successes_regressed": totals["previous_w6_successes_regressed"],
        "overall_w6_recovery_at_8": totals["w6_success_8"] / totals["trials"],
        "overall_w7_recovery_at_8": totals["w7_success_8"] / totals["trials"],
        "overall_recovery_delta_vs_w6": (
            totals["w7_success_8"] - totals["w6_success_8"]
        ) / totals["trials"],
        "minimum_primary_only_delta_vs_w6": min(row["primary_only_delta_vs_w6"] for row in rows),
        "minimum_retention_delta_12_minus_8": min(row["retention_delta_12_minus_8"] for row in rows),
        "minimum_causal_drop_when_witness_corrupted": min(row["causal_drop_when_witness_corrupted"] for row in rows),
        "zero_drive_exact_w6": all(row["zero_drive_exact_w6"] for row in rows),
        "adaptation_by_size": adaptation_by_size,
    }

    passes = (
        summary["diagnosed_pingpong_cases"] == spec["diagnosed_w6_pingpong_cases"]
        and summary["pingpong_cases_recovered_at_8"] >= gate["minimum_pingpong_cases_recovered_at_8"]
        and summary["pingpong_cases_recovered_at_12"] >= gate["minimum_pingpong_cases_recovered_at_12"]
        and summary["maximum_post_erasure_return_handoffs_per_pingpong_case"] <= gate["maximum_post_erasure_return_handoffs_per_pingpong_case"]
        and summary["previous_w6_successes_regressed"] <= gate["maximum_previous_w6_successes_regressed"]
        and summary["overall_recovery_delta_vs_w6"] >= gate["minimum_overall_recovery_delta_vs_w6"]
        and summary["minimum_primary_only_delta_vs_w6"] >= gate["minimum_primary_only_delta_vs_w6"]
        and summary["minimum_retention_delta_12_minus_8"] >= -gate["maximum_retention_drop_8_to_12"]
        and summary["minimum_causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted"]
        and (summary["zero_drive_exact_w6"] if gate["zero_drive_must_match_w6"] else True)
        and (all(adaptation_by_size.values()) if gate["adaptation_all_sizes"] else True)
    )

    return {
        "schema": spec["schema"],
        "development_only": True,
        "retunes_w6": False,
        "criteria": gate,
        "rows": rows,
        "pingpong_cases": pingpong_rows,
        "summary": summary,
        "passes": passes,
        "scope_boundary": spec["scope_boundary"],
    }


def main() -> None:
    print(json.dumps(run_probe(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
