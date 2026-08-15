"""Non-evidence development probe for MORPHOS-P1 path-gradient dynamics.

Seeds in this file are development-only and must not be reused for frozen
confirmation. The probe selects the minimum gradient gain satisfying all
predeclared transfer criteria across 5x5, 7x7, and 9x9 corpora.
"""
from __future__ import annotations

import json

from benchmarks.run_multimirror import (
    _fixed_binary_targets,
    _flip_binary,
    _noise_indices,
    _s2_components,
    _sha_binary_seeds,
)
from morphos.multimirror import MultiReflectiveGrid2D, MultiReflectiveLaw
from morphos.path_gradient import PathGradientGrid2D, PathGradientLaw

M2_LAW = MultiReflectiveLaw(
    local_coupling=0.15,
    domain_coupling=0.08,
    system_coupling=0.08,
    local_commit_delay=3,
    domain_commit_delay=4,
    system_commit_delay=5,
)

CORPORA = [
    {"width": 5, "height": 5, "seed": 202608154001, "samples": 96},
    {"width": 7, "height": 7, "seed": 202608154011, "samples": 96},
    {"width": 9, "height": 9, "seed": 202608154021, "samples": 72},
]
CANDIDATES = [0.25, 0.5, 0.75, 1.0]
RELAX_STEPS = 6
MAX_TARGETS = 12
TRIALS_PER_TARGET = 8

# Predeclared before observing this probe.
MIN_DOUBLE_GAIN_VS_M2 = 0.05
MIN_PRIMARY_GAIN_VS_M2 = -0.02
MAX_ABS_ALL_GAIN_VS_M2 = 0.05


def _case(target, index, config, hierarchy, *, gain=None, planes=()):
    cls = MultiReflectiveGrid2D if gain is None else PathGradientGrid2D
    kwargs = {
        "config": config,
        "law": hierarchy,
        "reflective_law": M2_LAW,
    }
    if gain is not None:
        kwargs["path_law"] = PathGradientLaw(gradient_gain=gain)
    model = cls(target, **kwargs)
    model.perturb_primary([index])
    if "local" in planes:
        model.perturb_local_mirror([index])
    if "domain" in planes:
        model.perturb_domain_mirror([index])
    if "system" in planes:
        model.perturb_system_mirror([index])
    model.run([0.0] * RELAX_STEPS)
    return model


def _corpus(gain, spec):
    width = spec["width"]
    height = spec["height"]
    config, hierarchy = _s2_components(
        {
            "frozen_s1": {"alpha": 0.25},
            "frozen_s2": {"beta": 0.06, "domain_size": 3},
        },
        width,
        height,
    )
    seeds = _sha_binary_seeds(spec["seed"], spec["samples"], width * height)
    targets = _fixed_binary_targets(seeds, config, hierarchy, RELAX_STEPS)[:MAX_TARGETS]
    if not targets:
        raise RuntimeError("development corpus produced no binary fixed targets")

    counts = {"m2_primary": 0, "p1_primary": 0, "m2_double": 0, "p1_double": 0, "m2_all": 0, "p1_all": 0}
    boosted_steps = 0
    trials = 0
    for target_index, target in enumerate(targets):
        indices = _noise_indices(spec["seed"], target_index, width * height, TRIALS_PER_TARGET)
        for index in indices:
            m2_primary = _case(target, index, config, hierarchy)
            p1_primary = _case(target, index, config, hierarchy, gain=gain)
            m2_double = _case(target, index, config, hierarchy, planes=("local",))
            p1_double = _case(target, index, config, hierarchy, gain=gain, planes=("local",))
            all_planes = ("local", "domain", "system")
            m2_all = _case(target, index, config, hierarchy, planes=all_planes)
            p1_all = _case(target, index, config, hierarchy, gain=gain, planes=all_planes)
            for key, model in (
                ("m2_primary", m2_primary),
                ("p1_primary", p1_primary),
                ("m2_double", m2_double),
                ("p1_double", p1_double),
                ("m2_all", m2_all),
                ("p1_all", p1_all),
            ):
                counts[key] += int(model.state_string() == target)
            boosted_steps += p1_primary.boosted_steps + p1_double.boosted_steps
            trials += 1

    rate = lambda key: counts[key] / trials
    return {
        "width": width,
        "height": height,
        "seed": spec["seed"],
        "trials": trials,
        "m2_primary": rate("m2_primary"),
        "p1_primary": rate("p1_primary"),
        "primary_gain_vs_m2": rate("p1_primary") - rate("m2_primary"),
        "m2_double": rate("m2_double"),
        "p1_double": rate("p1_double"),
        "double_gain_vs_m2": rate("p1_double") - rate("m2_double"),
        "m2_all": rate("m2_all"),
        "p1_all": rate("p1_all"),
        "all_gain_vs_m2": rate("p1_all") - rate("m2_all"),
        "mean_boosted_steps_per_primary_or_double_trial": boosted_steps / (2 * trials),
    }


def main():
    candidates = []
    selected = None
    for gain in CANDIDATES:
        rows = [_corpus(gain, spec) for spec in CORPORA]
        min_double = min(row["double_gain_vs_m2"] for row in rows)
        min_primary = min(row["primary_gain_vs_m2"] for row in rows)
        max_abs_all = max(abs(row["all_gain_vs_m2"]) for row in rows)
        passes = (
            min_double >= MIN_DOUBLE_GAIN_VS_M2
            and min_primary >= MIN_PRIMARY_GAIN_VS_M2
            and max_abs_all <= MAX_ABS_ALL_GAIN_VS_M2
        )
        item = {
            "gradient_gain": gain,
            "min_double_gain_vs_m2": min_double,
            "min_primary_gain_vs_m2": min_primary,
            "max_abs_all_gain_vs_m2": max_abs_all,
            "passes": passes,
            "rows": rows,
        }
        candidates.append(item)
        if selected is None and passes:
            selected = gain

    print(json.dumps({
        "development_only": True,
        "selection_rule": "minimum passing gradient_gain",
        "criteria": {
            "minimum_double_gain_vs_m2": MIN_DOUBLE_GAIN_VS_M2,
            "minimum_primary_gain_vs_m2": MIN_PRIMARY_GAIN_VS_M2,
            "maximum_absolute_all_corruption_gain_vs_m2": MAX_ABS_ALL_GAIN_VS_M2,
        },
        "candidates": candidates,
        "selected": selected,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
