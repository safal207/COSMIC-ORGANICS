"""Development-only gate for MORPHOS-W8.1 path margin completion."""
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
from morphos.witness_path_completion import PathCompletionAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w81_path_completion_manifest.json")


def _adaptation(config, hierarchy, mirror_law, cells: int, spec: dict) -> tuple[bool, int]:
    model = PathCompletionAuthorityGrid2D(
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
        and model.witness_signature() != initial,
        model.margin_completion_events,
    )


def run_probe() -> dict:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = _manifest()
    rows = []
    remaining = []
    totals = {
        "trials": 0,
        "v0_success_8": 0,
        "v81_success_8": 0,
        "v81_success_12": 0,
        "previous_v0_successes_regressed": 0,
        "remaining_source_endpoints_rescued": 0,
        "remaining_exact_failures_rescued": 0,
        "path_m_completion_cases_among_rescued": 0,
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
            "v0_8": 0,
            "v81_8": 0,
            "v81_12": 0,
            "corrupt_8": 0,
            "regressed": 0,
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
                v0_8 = _run(
                    MarginCompletionAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                v0_12 = _run(
                    MarginCompletionAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                v81_8 = _run(
                    PathCompletionAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    **kwargs,
                )
                v81_12 = _run(
                    PathCompletionAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                corrupt = _run(
                    PathCompletionAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    corrupt_witness=True,
                    **kwargs,
                )
                v0_ok8 = v0_8.state_string() == target
                v0_ok12 = v0_12.state_string() == target
                v81_ok8 = v81_8.state_string() == target
                v81_ok12 = v81_12.state_string() == target
                counts["trials"] += 1
                counts["v0_8"] += int(v0_ok8)
                counts["v81_8"] += int(v81_ok8)
                counts["v81_12"] += int(v81_ok12)
                counts["corrupt_8"] += int(corrupt.state_string() == target)
                counts["regressed"] += int(v0_ok8 and not v81_ok8)

                if not v0_ok12:
                    source_rescued = v81_12.states[source] == target[source]
                    exact_rescued = v81_ok12
                    m_completion = v81_12.path_completion_m_events > 0
                    totals["remaining_source_endpoints_rescued"] += int(source_rescued)
                    totals["remaining_exact_failures_rescued"] += int(exact_rescued)
                    totals["path_m_completion_cases_among_rescued"] += int(
                        exact_rescued and m_completion
                    )
                    remaining.append(
                        {
                            "width": width,
                            "height": height,
                            "seed": corpus["seed"],
                            "target_index": target_index,
                            "trial_index": trial_index,
                            "source": source,
                            "source_rescued_at_12": source_rescued,
                            "exact_recovered_at_8": v81_ok8,
                            "exact_recovered_at_12": exact_rescued,
                            "binary_completion_events": v81_12.path_completion_binary_events,
                            "m_completion_events": v81_12.path_completion_m_events,
                            "completion_total": v81_12.margin_completion_total,
                            "completion_max": v81_12.margin_completion_max,
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
                "w8_v0_recovery_at_8": rate("v0_8"),
                "w81_recovery_at_8": rate("v81_8"),
                "w81_recovery_at_12": rate("v81_12"),
                "delta_vs_v0_at_8": rate("v81_8") - rate("v0_8"),
                "previous_v0_successes_regressed": counts["regressed"],
                "causal_drop_when_witness_corrupted": rate("v81_8") - rate("corrupt_8"),
            }
        )
        totals["trials"] += n
        totals["v0_success_8"] += counts["v0_8"]
        totals["v81_success_8"] += counts["v81_8"]
        totals["v81_success_12"] += counts["v81_12"]
        totals["previous_v0_successes_regressed"] += counts["regressed"]

        size = f"{width}x{height}"
        if size not in adaptation_by_size:
            ok, events = _adaptation(config, hierarchy, mirror_law, cells, spec)
            adaptation_by_size[size] = {
                "passes": ok,
                "completion_events": events,
            }

    zero_completion_events = 0
    for corpus in spec["corpora"]:
        width = corpus["width"]
        cells = width * width
        config, hierarchy = _s2_components(base, width, width)
        target = _fixed_binary_targets(
            _sha_binary_seeds(corpus["seed"], corpus["samples"], cells),
            config,
            hierarchy,
            spec["target_discovery_steps"],
        )[0]
        source = _noise_indices(corpus["seed"], 0, cells, spec["trials_per_target"])[0]
        model = PathCompletionAuthorityGrid2D(
            target,
            config=config,
            law=hierarchy,
            reflective_law=_m2_law(base),
            witness_law=WitnessLaw(witness_drive=0.0, commit_delay=spec["witness_commit_delay"]),
        )
        _corrupt_all(model, source)
        model.run([0.0] * spec["retention_horizon"])
        zero_completion_events += model.margin_completion_events

    summary = {
        **totals,
        "diagnosed_v0_persistent_failures": len(remaining),
        "overall_v0_recovery_at_8": totals["v0_success_8"] / totals["trials"],
        "overall_v81_recovery_at_8": totals["v81_success_8"] / totals["trials"],
        "overall_v81_recovery_at_12": totals["v81_success_12"] / totals["trials"],
        "minimum_v81_recovery_at_8": min(row["w81_recovery_at_8"] for row in rows),
        "minimum_v81_recovery_at_12": min(row["w81_recovery_at_12"] for row in rows),
        "minimum_causal_drop_when_witness_corrupted": min(
            row["causal_drop_when_witness_corrupted"] for row in rows
        ),
        "zero_witness_completion_events": zero_completion_events,
        "adaptation_by_size": adaptation_by_size,
    }

    gate = spec["predeclared_gates"]
    passes = (
        len(remaining) == spec["diagnosed_w8_v0_persistent_failures"]
        and summary["remaining_source_endpoints_rescued"] >= gate["minimum_remaining_source_endpoints_rescued"]
        and summary["remaining_exact_failures_rescued"] >= gate["minimum_remaining_exact_failures_rescued"]
        and summary["previous_v0_successes_regressed"] <= gate["maximum_previous_w8_v0_successes_regressed"]
        and summary["path_m_completion_cases_among_rescued"] >= gate["minimum_path_m_completion_cases_among_rescued"]
        and summary["minimum_v81_recovery_at_8"] >= gate["minimum_recovery_at_8_every_corpus"]
        and summary["minimum_v81_recovery_at_12"] >= gate["minimum_recovery_at_12_every_corpus"]
        and summary["minimum_causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted_every_corpus"]
        and summary["zero_witness_completion_events"] == gate["zero_witness_completion_events"]
        and all(
            item["passes"]
            and item["completion_events"] == gate["adaptation_completion_events"]
            for item in adaptation_by_size.values()
        )
    )
    return {
        "schema": spec["schema"],
        "development_only": True,
        "independent_confirmation": False,
        "retunes_w8_v0": False,
        "criteria": gate,
        "rows": rows,
        "remaining_v0_failures": remaining,
        "summary": summary,
        "passes": passes,
        "scope_boundary": spec["scope_boundary"],
    }


def main() -> None:
    report = run_probe()
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["passes"]:
        raise SystemExit("MORPHOS-W8.1 development gate failed")


if __name__ == "__main__":
    main()
