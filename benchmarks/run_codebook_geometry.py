"""MORPHOS-S3: analyze sampled attractor codebook geometry without retuning dynamics."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

from benchmarks.run_hierarchical import _hierarchical_relax
from benchmarks.run_scale_aware import (
    _base_config,
    _binary_fixed,
    _grid_relax,
    _majority_relax,
    _sha_binary_seeds,
)
from morphos.hierarchical import HierarchicalLaw
from morphos.scale_aware import ScaleLaw

DEFAULT_MANIFEST = Path(__file__).with_name("codebook_manifest.json")


def hamming(a: str, b: str) -> int:
    if len(a) != len(b):
        raise ValueError("states must have equal length")
    return sum(left != right for left, right in zip(a, b))


def flip_one(state: str, index: int) -> str:
    if not 0 <= index < len(state):
        raise IndexError(index)
    values = list(state)
    values[index] = "C" if values[index] == "A" else "A"
    return "".join(values)


def codebook_geometry(codewords: list[str]) -> dict[str, Any]:
    words = sorted(set(codewords))
    if not words:
        return {
            "codebook_size": 0,
            "capacity_bits": 0.0,
            "min_distance": None,
            "mean_nearest_distance": None,
            "distance1_pair_count": 0,
            "distance2_pair_count": 0,
            "codewords_with_distance1_neighbor": 0,
            "distance3_single_bit_guarantee": False,
        }

    nearest: dict[str, int | None] = {word: None for word in words}
    distance1_pairs = 0
    distance2_pairs = 0
    min_distance: int | None = None
    for left_index, left in enumerate(words):
        for right in words[left_index + 1 :]:
            distance = hamming(left, right)
            if min_distance is None or distance < min_distance:
                min_distance = distance
            if distance == 1:
                distance1_pairs += 1
            elif distance == 2:
                distance2_pairs += 1
            for word in (left, right):
                current = nearest[word]
                if current is None or distance < current:
                    nearest[word] = distance

    nearest_values = [value for value in nearest.values() if value is not None]
    distance1_words = sum(value == 1 for value in nearest.values())
    return {
        "codebook_size": len(words),
        "capacity_bits": round(math.log2(len(words)), 12),
        "min_distance": min_distance,
        "mean_nearest_distance": round(
            sum(nearest_values) / len(nearest_values), 12
        ) if nearest_values else None,
        "distance1_pair_count": distance1_pairs,
        "distance2_pair_count": distance2_pairs,
        "codewords_with_distance1_neighbor": distance1_words,
        "distance3_single_bit_guarantee": bool(
            min_distance is not None and min_distance >= 3
        ),
    }


def _trial_key(seed: int, model_name: str, target: str, bit: int) -> bytes:
    return hashlib.sha256(
        f"{seed}:{model_name}:{target}:{bit}".encode("ascii")
    ).digest()


def one_bit_geometry_trials(
    codewords: list[str],
    relax: Callable[[str], tuple[str, int]],
    *,
    seed: int,
    model_name: str,
    trial_cap: int,
) -> dict[str, Any]:
    words = sorted(set(codewords))
    if not words:
        return {
            "trials": 0,
            "unique_nearest_fraction": 0.0,
            "nearest_ambiguity_fraction": 0.0,
            "direct_codeword_collision_fraction": 0.0,
            "dynamic_recovery": 0.0,
            "dynamic_recovery_on_unique_nearest": None,
            "dynamic_recovery_on_ambiguous": None,
            "dynamic_recovery_on_direct_collision": None,
            "hard_collision_failures": 0,
            "recovery_failures": 0,
            "hard_collision_share_of_failures": 0.0,
        }

    word_set = set(words)
    candidates: list[tuple[bytes, str, int, str]] = []
    for target in words:
        for bit in range(len(target)):
            corrupted = flip_one(target, bit)
            candidates.append(
                (_trial_key(seed, model_name, target, bit), target, bit, corrupted)
            )
    if len(candidates) > trial_cap:
        candidates = sorted(candidates, key=lambda item: item[0])[:trial_cap]

    total = len(candidates)
    unique_count = 0
    ambiguous_count = 0
    collision_count = 0
    recovered = 0
    unique_recovered = 0
    ambiguous_recovered = 0
    collision_recovered = 0

    for _, target, _, corrupted in candidates:
        distances = [hamming(corrupted, word) for word in words]
        minimum = min(distances)
        nearest_count = sum(distance == minimum for distance in distances)
        target_index = words.index(target)
        target_is_unique_nearest = (
            distances[target_index] == minimum and nearest_count == 1
        )
        ambiguous = nearest_count > 1
        direct_collision = corrupted in word_set and corrupted != target

        final, _ = relax(corrupted)
        success = final == target

        unique_count += int(target_is_unique_nearest)
        ambiguous_count += int(ambiguous)
        collision_count += int(direct_collision)
        recovered += int(success)
        unique_recovered += int(success and target_is_unique_nearest)
        ambiguous_recovered += int(success and ambiguous)
        collision_recovered += int(success and direct_collision)

    failures = total - recovered
    hard_collision_failures = collision_count - collision_recovered
    return {
        "trials": total,
        "unique_nearest_fraction": round(unique_count / total, 12),
        "nearest_ambiguity_fraction": round(ambiguous_count / total, 12),
        "direct_codeword_collision_fraction": round(collision_count / total, 12),
        "dynamic_recovery": round(recovered / total, 12),
        "dynamic_recovery_on_unique_nearest": round(
            unique_recovered / unique_count, 12
        ) if unique_count else None,
        "dynamic_recovery_on_ambiguous": round(
            ambiguous_recovered / ambiguous_count, 12
        ) if ambiguous_count else None,
        "dynamic_recovery_on_direct_collision": round(
            collision_recovered / collision_count, 12
        ) if collision_count else None,
        "hard_collision_failures": hard_collision_failures,
        "recovery_failures": failures,
        "hard_collision_share_of_failures": round(
            hard_collision_failures / failures, 12
        ) if failures else 0.0,
    }


def analyze_model(
    seeds: list[str],
    relax: Callable[[str], tuple[str, int]],
    *,
    seed: int,
    model_name: str,
    trial_cap: int,
) -> dict[str, Any]:
    _, binary, _ = _binary_fixed(seeds, relax)
    words = sorted(binary)
    geometry = codebook_geometry(words)
    trials = one_bit_geometry_trials(
        words,
        relax,
        seed=seed,
        model_name=model_name,
        trial_cap=trial_cap,
    )
    return {"geometry": geometry, "one_bit": trials}


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 12) if values else None


def run_suite(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base = _base_config(manifest["frozen_candidate"])
    steps = manifest["relax_steps"]
    scale_spec = manifest["s1_scale_law"]
    hierarchy_spec = manifest["s2_hierarchy_law"]
    s1_law = ScaleLaw(
        reference_linear_size=scale_spec["reference_linear_size"],
        exponent=scale_spec["exponent"],
    )
    s2_law = HierarchicalLaw(
        reference_linear_size=hierarchy_spec["reference_linear_size"],
        exponent=hierarchy_spec["exponent"],
        domain_size=hierarchy_spec["domain_size"],
    )
    spec = manifest["analysis"]
    trial_cap = spec["trial_cap_per_model_corpus"]

    corpora: list[dict[str, Any]] = []
    for size in spec["sizes"]:
        width, height = size["width"], size["height"]
        scaled = s1_law.apply(base, width=width, height=height)
        relaxers = {
            "majority_ca": _majority_relax(width, height, steps),
            "s1": _grid_relax(scaled, steps),
            "s2": _hierarchical_relax(scaled, s2_law, steps),
        }
        for seed in size["seeds"]:
            initial = _sha_binary_seeds(seed, size["samples"], width * height)
            models = {
                name: analyze_model(
                    initial,
                    relaxer,
                    seed=seed,
                    model_name=name,
                    trial_cap=trial_cap,
                )
                for name, relaxer in relaxers.items()
            }
            corpora.append({
                "width": width,
                "height": height,
                "seed": seed,
                "samples": size["samples"],
                "models": models,
            })

    s2_rows = [item["models"]["s2"] for item in corpora]
    s2_large_rows = [
        item["models"]["s2"] for item in corpora if item["width"] > 5
    ]
    majority_rows = [item["models"]["majority_ca"] for item in corpora]
    s1_rows = [item["models"]["s1"] for item in corpora]

    collision_rows = [
        row for row in s2_rows
        if row["one_bit"]["direct_codeword_collision_fraction"] > 0
    ]
    unique_minus_ambiguous = []
    for row in s2_rows:
        unique = row["one_bit"]["dynamic_recovery_on_unique_nearest"]
        ambiguous = row["one_bit"]["dynamic_recovery_on_ambiguous"]
        if unique is not None and ambiguous is not None:
            unique_minus_ambiguous.append(unique - ambiguous)

    summary = {
        "corpora": len(corpora),
        "s2_distance3_guarantee_corpora": sum(
            row["geometry"]["distance3_single_bit_guarantee"]
            for row in s2_rows
        ),
        "s2_large_scale_distance3_guarantee_corpora": sum(
            row["geometry"]["distance3_single_bit_guarantee"]
            for row in s2_large_rows
        ),
        "s2_direct_collision_corpora": len(collision_rows),
        "s2_large_scale_direct_collision_corpora": sum(
            row["one_bit"]["direct_codeword_collision_fraction"] > 0
            for row in s2_large_rows
        ),
        "s2_mean_min_distance": _mean([
            float(row["geometry"]["min_distance"])
            for row in s2_rows if row["geometry"]["min_distance"] is not None
        ]),
        "s2_large_scale_mean_unique_nearest_fraction": _mean([
            row["one_bit"]["unique_nearest_fraction"]
            for row in s2_large_rows
        ]),
        "s2_large_scale_mean_direct_collision_fraction": _mean([
            row["one_bit"]["direct_codeword_collision_fraction"]
            for row in s2_large_rows
        ]),
        "s2_large_scale_mean_dynamic_recovery": _mean([
            row["one_bit"]["dynamic_recovery"]
            for row in s2_large_rows
        ]),
        "s2_mean_unique_minus_ambiguous_recovery": _mean(
            unique_minus_ambiguous
        ),
        "s2_collision_trials_never_recover": all(
            row["one_bit"]["dynamic_recovery_on_direct_collision"] == 0.0
            for row in collision_rows
        ) if collision_rows else True,
        "s2_geometry_blocks_global_one_bit_guarantee": any(
            not row["geometry"]["distance3_single_bit_guarantee"]
            for row in s2_rows
        ),
        "baseline_mean_min_distance": {
            "majority_ca": _mean([
                float(row["geometry"]["min_distance"])
                for row in majority_rows
                if row["geometry"]["min_distance"] is not None
            ]),
            "s1": _mean([
                float(row["geometry"]["min_distance"])
                for row in s1_rows
                if row["geometry"]["min_distance"] is not None
            ]),
            "s2": _mean([
                float(row["geometry"]["min_distance"])
                for row in s2_rows
                if row["geometry"]["min_distance"] is not None
            ]),
        },
    }
    if summary["s2_direct_collision_corpora"]:
        interpretation = "sampled_s2_codebook_has_direct_one_bit_codeword_collisions"
    elif summary["s2_geometry_blocks_global_one_bit_guarantee"]:
        interpretation = "sampled_s2_codebook_lacks_distance3_one_bit_guarantee"
    else:
        interpretation = "sampled_s2_codebook_supports_distance3_one_bit_guarantee"
    summary["interpretation"] = interpretation

    return {
        "schema_version": "cosmic-organics/codebook-result-0.1",
        "suite_id": manifest["suite_id"],
        "selection_rule": spec["selection_rule"],
        "scientific_boundary": (
            "sampled binary fixed-attractor geometry only; not exhaustive channel "
            "capacity, not a quantum code, and not a physical error model"
        ),
        "corpora": corpora,
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(run_suite(args.manifest), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
