"""Development-only gate for MORPHOS-W6 erasure-aware witness.

The mechanism is tested on the already diagnosed W5 confirmation corpora, so
this is not independent confirmation. Parameters and horizons remain frozen;
only observability of exactly one known `M` erasure is changed.
"""
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
from morphos.witness_erasure import ErasureAwareAuthorityGrid2D
from morphos.witness_handoff import HandoffAuthorityGrid2D

MANIFEST = Path(__file__).with_name("w6_erasure_manifest.json")


def _diff_indices(model, target: str) -> list[int]:
    return [
        index
        for index, (actual, expected) in enumerate(zip(model.states, target))
        if actual != expected
    ]


def _is_diagnosed_mixed_erasure(w5_8, w5_12, target: str, source: int) -> bool:
    diff8 = _diff_indices(w5_8, target)
    diff12 = _diff_indices(w5_12, target)
    return (
        w5_8.states[source] == target[source]
        and w5_8.handoff_events == 0
        and w5_12.handoff_events == 0
        and len(diff8) == 1
        and len(diff12) == 1
        and diff8 == diff12
        and diff8[0] != source
        and w5_8.states[diff8[0]] == "M"
        and w5_12.states[diff12[0]] == "M"
    )


def _is_diagnosed_multi_error_ambiguous(w5_8, w5_12, target: str, source: int) -> bool:
    diff8 = _diff_indices(w5_8, target)
    diff12 = _diff_indices(w5_12, target)
    return (
        w5_8.states[source] == target[source]
        and w5_8.state_string() != target
        and w5_8.handoff_events == 0
        and w5_12.handoff_events == 0
        and not (
            len(diff8) == 1
            and len(diff12) == 1
            and diff8 == diff12
            and w5_8.states[diff8[0]] == "M"
            and w5_12.states[diff12[0]] == "M"
        )
    )


def _adaptation(config, hierarchy, mirror_law, cells: int, spec: dict) -> bool:
    model = ErasureAwareAuthorityGrid2D(
        "A" * cells,
        config=config,
        law=hierarchy,
        reflective_law=mirror_law,
    )
    # Use the frozen witness parameters explicitly after construction.
    model.witness_law = type(model.witness_law)(
        witness_drive=spec["witness_drive"],
        commit_delay=spec["witness_commit_delay"],
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
    aggregate = {
        "trials": 0,
        "w5_success_8": 0,
        "w6_success_8": 0,
        "previous_w5_successes_regressed": 0,
        "mixed_erasure_cases": 0,
        "mixed_erasure_handoff_cases": 0,
        "mixed_erasure_cases_rescued_at_8": 0,
        "multi_error_ambiguous_cases": 0,
        "false_erasure_decodes_on_multi_error": 0,
    }
    corpus_rows = []
    adaptation_by_size: dict[str, bool] = {}

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
            "w5_8": 0,
            "w6_8": 0,
            "w6_12": 0,
            "corrupt_8": 0,
            "w5_primary_8": 0,
            "w6_primary_8": 0,
            "w5_zero_8": 0,
            "w6_zero_8": 0,
            "regressed": 0,
        }

        for target_index, target in enumerate(targets):
            indices = _noise_indices(
                corpus["seed"], target_index, cells, spec["trials_per_target"]
            )
            for source in indices:
                one = [source]
                kwargs = dict(
                    target=target,
                    indices=one,
                    config=config,
                    hierarchy=hierarchy,
                    m2_law=mirror_law,
                    witness_drive=spec["witness_drive"],
                    witness_commit_delay=spec["witness_commit_delay"],
                )
                w5 = _run(
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
                w6_12 = _run(
                    ErasureAwareAuthorityGrid2D,
                    horizon=spec["retention_horizon"],
                    **kwargs,
                )
                corrupt = _run(
                    ErasureAwareAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    corrupt_witness=True,
                    **kwargs,
                )
                w5_primary = _run(
                    HandoffAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    common=False,
                    **kwargs,
                )
                w6_primary = _run(
                    ErasureAwareAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    common=False,
                    **kwargs,
                )
                w5_zero = _run(
                    HandoffAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    zero_drive=True,
                    **kwargs,
                )
                w6_zero = _run(
                    ErasureAwareAuthorityGrid2D,
                    horizon=spec["evaluation_horizon"],
                    zero_drive=True,
                    **kwargs,
                )

                w5_ok = w5.state_string() == target
                w6_ok = w6.state_string() == target
                mixed_case = _is_diagnosed_mixed_erasure(
                    w5, w5_12, target, source
                )
                multi_case = _is_diagnosed_multi_error_ambiguous(
                    w5, w5_12, target, source
                )

                aggregate["trials"] += 1
                aggregate["w5_success_8"] += int(w5_ok)
                aggregate["w6_success_8"] += int(w6_ok)
                aggregate["previous_w5_successes_regressed"] += int(
                    w5_ok and not w6_ok
                )
                if mixed_case:
                    aggregate["mixed_erasure_cases"] += 1
                    aggregate["mixed_erasure_handoff_cases"] += int(
                        w6.erasure_handoff_events > 0
                    )
                    aggregate["mixed_erasure_cases_rescued_at_8"] += int(w6_ok)
                if multi_case:
                    aggregate["multi_error_ambiguous_cases"] += 1
                    aggregate["false_erasure_decodes_on_multi_error"] += int(
                        w6.erasure_handoff_events > 0
                    )

                counts["trials"] += 1
                counts["w5_8"] += int(w5_ok)
                counts["w6_8"] += int(w6_ok)
                counts["w6_12"] += int(w6_12.state_string() == target)
                counts["corrupt_8"] += int(corrupt.state_string() == target)
                counts["w5_primary_8"] += int(w5_primary.state_string() == target)
                counts["w6_primary_8"] += int(w6_primary.state_string() == target)
                counts["w5_zero_8"] += int(w5_zero.state_string() == target)
                counts["w6_zero_8"] += int(w6_zero.state_string() == target)
                counts["regressed"] += int(w5_ok and not w6_ok)

        n = counts["trials"]
        rate = lambda key: counts[key] / n
        corpus_rows.append(
            {
                "width": width,
                "height": height,
                "seed": corpus["seed"],
                "trials": n,
                "w5_recovery_at_8": rate("w5_8"),
                "w6_recovery_at_8": rate("w6_8"),
                "w6_recovery_at_12": rate("w6_12"),
                "delta_vs_w5_at_8": rate("w6_8") - rate("w5_8"),
                "previous_w5_successes_regressed": counts["regressed"],
                "retention_delta_12_minus_8": rate("w6_12") - rate("w6_8"),
                "causal_drop_when_witness_corrupted": rate("w6_8") - rate("corrupt_8"),
                "primary_only_delta_vs_w5": rate("w6_primary_8") - rate("w5_primary_8"),
                "zero_drive_exact_w5": counts["w6_zero_8"] == counts["w5_zero_8"],
            }
        )

        size_key = f"{width}x{height}"
        if size_key not in adaptation_by_size:
            adaptation_by_size[size_key] = _adaptation(
                config, hierarchy, mirror_law, cells, spec
            )

    gate = spec["predeclared_gates"]
    total = aggregate["trials"]
    summary = {
        **aggregate,
        "overall_w5_recovery_at_8": aggregate["w5_success_8"] / total,
        "overall_w6_recovery_at_8": aggregate["w6_success_8"] / total,
        "overall_recovery_delta_vs_w5": (
            aggregate["w6_success_8"] - aggregate["w5_success_8"]
        ) / total,
        "minimum_primary_only_delta_vs_w5": min(
            row["primary_only_delta_vs_w5"] for row in corpus_rows
        ),
        "minimum_retention_delta_12_minus_8": min(
            row["retention_delta_12_minus_8"] for row in corpus_rows
        ),
        "minimum_causal_drop_when_witness_corrupted": min(
            row["causal_drop_when_witness_corrupted"] for row in corpus_rows
        ),
        "zero_drive_exact_w5": all(
            row["zero_drive_exact_w5"] for row in corpus_rows
        ),
        "adaptation_by_size": adaptation_by_size,
    }

    passes = (
        summary["mixed_erasure_cases"] == spec["diagnosed_mixed_erasure_cases"]
        and summary["multi_error_ambiguous_cases"] == spec["diagnosed_multi_error_ambiguous_cases"]
        and summary["mixed_erasure_handoff_cases"] >= gate["minimum_erasure_handoff_cases"]
        and summary["mixed_erasure_cases_rescued_at_8"] >= gate["minimum_mixed_erasure_cases_rescued_at_8"]
        and summary["previous_w5_successes_regressed"] <= gate["maximum_previous_w5_successes_regressed"]
        and summary["overall_recovery_delta_vs_w5"] >= gate["minimum_overall_recovery_delta_vs_w5"]
        and summary["minimum_primary_only_delta_vs_w5"] >= gate["minimum_primary_only_delta_vs_w5"]
        and summary["minimum_retention_delta_12_minus_8"] >= -gate["maximum_retention_drop_8_to_12"]
        and summary["minimum_causal_drop_when_witness_corrupted"] >= gate["minimum_causal_drop_when_witness_corrupted"]
        and summary["false_erasure_decodes_on_multi_error"] <= gate["maximum_false_erasure_decodes_on_diagnosed_multi_error_case"]
        and (summary["zero_drive_exact_w5"] if gate["zero_drive_must_match_w5"] else True)
        and (all(adaptation_by_size.values()) if gate["adaptation_all_sizes"] else True)
    )

    return {
        "schema": spec["schema"],
        "development_only": True,
        "retunes_w5": False,
        "criteria": gate,
        "rows": corpus_rows,
        "summary": summary,
        "passes": passes,
        "scope_boundary": spec["scope_boundary"],
    }


def main() -> None:
    print(json.dumps(run_probe(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
