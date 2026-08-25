from __future__ import annotations

import json
from pathlib import Path

from benchmarks.cosmic_hw_10_oracle import derive_oracle

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "cosmic_hw_11_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_parent_hw10_oracle_is_exactly_reproduced() -> None:
    r = derive_oracle()
    assert r["source_sequences"] == 320
    assert r["real_leaves"] == 4240
    assert r["tree_count"] == 444
    assert r["padding_leaves"] == 2864
    assert r["parent_hashes"] == 6660
    assert r["parent_compression_blocks"] == 13320
    assert r["parent_sha_rounds"] == 852480
    assert r["proof_fragments"] == 16960
    assert r["verified_real_leaf_proofs"] == 4240
    assert r["oracle_fingerprint"] == "b716b577e7b7efa7e0ccb4f1c92f2b51a1d219e33d0f125e7ce461e656929978"


def test_factorial_systems_are_frozen() -> None:
    m = load_manifest()
    assert m["systems"] == {
        "B1_M1_CONTROL": {"tree_buffers": 1, "merkle_sha_engines": 1},
        "B2_M1": {"tree_buffers": 2, "merkle_sha_engines": 1},
        "B1_M2": {"tree_buffers": 1, "merkle_sha_engines": 2},
        "B2_M2": {"tree_buffers": 2, "merkle_sha_engines": 2},
    }
    assert m["semantic_contract"]["tree_leaf_capacity"] == 16
    assert m["semantic_contract"]["proof_levels"] == 4
    assert m["semantic_contract"]["parent_message_bytes"] == 65
    assert m["semantic_contract"]["parent_sha_blocks"] == 2
    assert m["semantic_contract"]["proof_serializer_lanes"] == 1


def test_m2_dependency_schedule_is_frozen() -> None:
    m = load_manifest()["m2_schedule"]
    assert m["parents_per_level"] == [8, 4, 2, 1]
    assert m["waves_per_level"] == [4, 2, 1, 1]
    assert m["waves_per_tree"] == 8
    assert m["total_waves"] == 444 * 8 == 3552
    assert m["ideal_parent_round_wall_cycles_per_tree_excluding_handshake"] == 8 * 2 * 64 == 1024
    assert m["ideal_parent_round_wall_cycles_total_excluding_handshake"] == 444 * 1024 == 454656
    assert m["next_level_requires_current_level_complete"] is True


def test_control_and_eligibility_are_frozen() -> None:
    m = load_manifest()
    c = m["control_hw10"]
    assert c["physical_cycles"] == 1027209
    assert c["backpressure_stalls"] == {
        "0.01": 0,
        "0.05": 542,
        "0.20": 11184,
        "1.00": 13456,
        "stress": 80560,
    }
    assert c["leaf_to_tree_stalls"] == 230795
    assert c["merkle_sha_busy_cycles"] == 852480
    assert c["lut"] == 36907
    assert c["ff"] == 21380
    assert c["core_cells_excluding_io"] == 62125
    assert c["logic_depth_proxy"] == 266

    e = m["eligibility"]
    assert e["max_stalls_1pct"] == 0
    assert e["max_stalls_5pct"] == 542
    assert e["max_physical_cycles"] == 719046
    assert e["min_physical_cycle_reduction_fraction"] == 0.30
    assert e["max_stress_stalls"] == 80560
    assert e["max_logic_depth_proxy"] == 266
    assert e["no_drops"] is True
    assert e["no_unbounded_queue"] is True
    assert e["proof_order_preserved"] is True


def test_no_synthetic_score_and_handoff_order_is_frozen() -> None:
    m = load_manifest()
    assert m["synthetic_combined_score"] is False
    assert m["handoff_tiebreak"] == [
        "minimum_core_cells_excluding_io",
        "minimum_ff",
        "minimum_lut",
        "minimum_physical_cycles",
        "minimum_logic_depth_proxy",
    ]


def test_candidate_files_do_not_exist_on_prereg_head() -> None:
    m = load_manifest()
    assert not (ROOT / m["candidate_rtl_path"]).exists()
    assert not (ROOT / m["candidate_benchmark_path"]).exists()
