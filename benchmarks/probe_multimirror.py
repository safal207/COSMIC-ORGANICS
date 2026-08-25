"""Non-evidence development probe for MORPHOS-M2 coupling selection.

Seeds in this file are development-only and must never be reused by the
confirmation suite.
"""
from __future__ import annotations

import json

from benchmarks.run_reflective import (
    _fixed_binary_targets,
    _flip_binary,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.hierarchical import HierarchicalGrid2D
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw
from morphos.reflective import ReflectiveGrid2D, ReflectiveLaw

DEV_CORPORA = [
    {"width": 5, "height": 5, "seed": 202608152001, "samples": 28},
    {"width": 7, "height": 7, "seed": 202608152011, "samples": 24},
    {"width": 9, "height": 9, "seed": 202608152021, "samples": 20},
]
CANDIDATES = [0.06, 0.08, 0.10, 0.12, 0.14, 0.16]
RELAX_STEPS = 6
MAX_TARGETS = 12
TRIALS_PER_TARGET = 4

BASE_MANIFEST = {
    "frozen_s2": {
        "base_candidate": {
            "adaptive_coupling": 0.5,
            "adaptive_threshold": 0.35,
            "anchor_coupling": 0.75,
            "anchor_threshold": 0.5,
            "mask": "checkerboard",
            "memory_decay": 0.0,
            "mixed_relax_threshold": 0.05,
            "neighborhood": "von_neumann",
        },
        "domain_size": 3,
        "hierarchy_exponent": 0.06,
        "reference_linear_size": 5.0,
        "scale_exponent": 0.25,
    }
}


def _metrics(coupling: float, corpus: dict) -> dict:
    width = corpus["width"]
    height = corpus["height"]
    seed = corpus["seed"]
    config, hierarchy = _s2_components(BASE_MANIFEST, width, height)
    seeds = _sha_binary_seeds(seed, corpus["samples"], width * height)
    targets = _fixed_binary_targets(seeds, config, hierarchy, RELAX_STEPS)[:MAX_TARGETS]
    if not targets:
        raise RuntimeError("development corpus produced no binary targets")

    recovered_s2 = 0
    recovered_m1_primary = 0
    recovered_m1_co = 0
    recovered_m2_primary = 0
    recovered_m2_double = 0
    recovered_m2_triple = 0
    recovered_m2_all = 0
    trials = 0

    m1_law = ReflectiveLaw(mirror_coupling=0.15, commit_delay=3)
    m2_law = MultiReflectiveLaw(
        local_coupling=0.15,
        domain_coupling=coupling,
        system_coupling=coupling,
        local_commit_delay=3,
        domain_commit_delay=4,
        system_commit_delay=5,
    )

    for target_index, target in enumerate(targets):
        indices = _noise_indices(
            seed, target_index, width * height, TRIALS_PER_TARGET
        )
        for index in indices:
            corrupted = _flip_binary(target, index)

            s2 = HierarchicalGrid2D(corrupted, config=config, law=hierarchy)
            s2.run([0.0] * RELAX_STEPS)

            m1 = ReflectiveGrid2D(
                target, config=config, law=hierarchy, reflective_law=m1_law
            )
            m1.perturb_primary([index])
            m1.run([0.0] * RELAX_STEPS)

            m1_co = ReflectiveGrid2D(
                target, config=config, law=hierarchy, reflective_law=m1_law
            )
            m1_co.perturb_primary([index])
            m1_co.perturb_mirror([index])
            m1_co.run([0.0] * RELAX_STEPS)

            def m2_case(*planes: str) -> MultiReflectiveGrid2D:
                model = MultiReflectiveGrid2D(
                    target,
                    config=config,
                    law=hierarchy,
                    reflective_law=m2_law,
                )
                model.perturb_primary([index])
                if "local" in planes:
                    model.perturb_local_mirror([index])
                if "domain" in planes:
                    model.perturb_domain_mirror([index])
                if "system" in planes:
                    model.perturb_system_mirror([index])
                model.run([0.0] * RELAX_STEPS)
                return model

            m2_primary = m2_case()
            m2_double = m2_case("local")
            m2_triple = m2_case("local", "domain")
            m2_all = m2_case("local", "domain", "system")

            recovered_s2 += int(s2.state_string() == target)
            recovered_m1_primary += int(m1.state_string() == target)
            recovered_m1_co += int(m1_co.state_string() == target)
            recovered_m2_primary += int(m2_primary.state_string() == target)
            recovered_m2_double += int(m2_double.state_string() == target)
            recovered_m2_triple += int(m2_triple.state_string() == target)
            recovered_m2_all += int(m2_all.state_string() == target)
            trials += 1

    def rate(value: int) -> float:
        return value / trials

    s2 = rate(recovered_s2)
    m1_primary = rate(recovered_m1_primary)
    m1_co = rate(recovered_m1_co)
    m2_primary = rate(recovered_m2_primary)
    m2_double = rate(recovered_m2_double)
    m2_triple = rate(recovered_m2_triple)
    m2_all = rate(recovered_m2_all)
    return {
        "width": width,
        "height": height,
        "seed": seed,
        "targets": len(targets),
        "trials": trials,
        "s2": s2,
        "m1_primary": m1_primary,
        "m1_co": m1_co,
        "m2_primary": m2_primary,
        "m2_double": m2_double,
        "m2_triple": m2_triple,
        "m2_all": m2_all,
        "primary_gain_vs_m1": m2_primary - m1_primary,
        "double_gain_vs_m1_co": m2_double - m1_co,
        "triple_gain_vs_m1_co": m2_triple - m1_co,
        "all_gain_vs_s2": m2_all - s2,
    }


def main() -> None:
    candidates = []
    selected = None
    for coupling in CANDIDATES:
        rows = [_metrics(coupling, corpus) for corpus in DEV_CORPORA]
        aggregate = {
            "secondary_coupling": coupling,
            "min_primary_gain_vs_m1": min(r["primary_gain_vs_m1"] for r in rows),
            "min_double_gain_vs_m1_co": min(r["double_gain_vs_m1_co"] for r in rows),
            "min_triple_gain_vs_m1_co": min(r["triple_gain_vs_m1_co"] for r in rows),
            "max_abs_all_gain_vs_s2": max(abs(r["all_gain_vs_s2"]) for r in rows),
            "rows": rows,
        }
        aggregate["passes"] = (
            aggregate["min_primary_gain_vs_m1"] >= -0.05
            and aggregate["min_double_gain_vs_m1_co"] >= 0.15
            and aggregate["min_triple_gain_vs_m1_co"] >= 0.05
            and aggregate["max_abs_all_gain_vs_s2"] <= 0.05
        )
        candidates.append(aggregate)
        if selected is None and aggregate["passes"]:
            selected = coupling

    print(json.dumps({"selected": selected, "candidates": candidates}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
