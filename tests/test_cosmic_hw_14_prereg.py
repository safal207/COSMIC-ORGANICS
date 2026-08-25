from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_14_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_parent_and_physical_target_are_frozen() -> None:
    manifest = load_manifest()
    assert manifest["experiment_id"] == "COSMIC-HW-14/v0.1"
    assert manifest["tracking_issue"] == 101

    parent = manifest["parent"]
    assert parent["source_head"] == "773b68597b9136c12867ecc1a3a1749edcba1627"
    assert parent["canonical_run"] == 32853523449
    assert parent["canonical_job"] == 97819854308
    assert parent["decision"] == "DEVICE_CAPACITY_NOT_SUPPORTED"
    assert parent["full_profile_capacity"] == {
        "comb_used": 116535,
        "comb_available": 83640,
        "ff_fraction": 0.35,
        "mult_used": 201,
        "mult_available": 156,
        "routed_seeds": 0,
        "frozen_seed_count": 5,
    }

    target = manifest["target"]
    assert target["device"] == "LFE5U-85F-8BG381C"
    assert target["density_flag"] == "--85k"
    assert target["package"] == "CABGA381"
    assert target["speed_grade"] == 8
    assert target["requested_clock_mhz"] == 10.0
    assert target["larger_device_fallback_allowed"] is False
    assert manifest["placement_seeds"] == [1401, 1402, 1403, 1404, 1405]


def test_three_existing_evidence_profiles_are_frozen() -> None:
    manifest = load_manifest()
    profiles = manifest["profiles"]
    assert [(p["tier"], p["id"]) for p in profiles] == [
        (1, "CORE_LITE_R40"),
        (2, "PROOF_EDGE_SHA1"),
        (3, "FULL_PROOF_HMAC"),
    ]

    expected_modules = {
        "CORE_LITE_R40": "cosmic_hw07_mesh64_receipt",
        "PROOF_EDGE_SHA1": "cosmic_hw08_sparse_receipt_sha256",
        "FULL_PROOF_HMAC": "cosmic_hw12_b1_m2_hmacx1",
    }
    for profile in profiles:
        assert profile["top_module"] == expected_modules[profile["id"]]
        assert profile["source_files"]
        for relative in profile["source_files"]:
            path = ROOT / relative
            assert path.exists(), relative
        top_source = "\n".join(
            (ROOT / relative).read_text(encoding="utf-8")
            for relative in profile["source_files"]
        )
        assert f"module {profile['top_module']}" in top_source

    core = profiles[0]
    assert core["parameters"] == {"SPARSE": 1, "FIFO_DEPTH": 4}
    assert core["forbidden_on_core"] == ["SHA-256", "Merkle", "HMAC"]

    edge = profiles[1]
    assert edge["forbidden_on_core"] == ["Merkle", "HMAC"]

    full = profiles[2]
    assert full["redesign_allowed"] is False


def test_harness_and_headroom_rules_are_frozen() -> None:
    manifest = load_manifest()
    harness = manifest["physical_harness"]
    assert harness["external_pins"] == ["clk", "reset", "status[7:0]"]
    assert harness["dynamic_stimulus_bits"] == 512
    assert harness["tick_valid_held_until_ready"] is True
    assert harness["dynamic_flush_and_sequence_controls"] is True
    assert harness["dynamic_sink_ready"] is True
    assert harness["major_outputs_feed_rolling_checksum"] is True
    assert harness["checksum_feedback_allowed"] is False
    assert harness["expected_answer_rom_allowed"] is False

    route = manifest["route_deployable_gate"]
    assert route["minimum_successful_routes"] == 3
    assert route["minimum_nonempty_bitstreams"] == 3
    assert route["minimum_10mhz_timing_passes"] == 3
    assert route["frozen_seed_count"] == 5

    headroom = manifest["board_handoff_headroom"]
    assert headroom == {
        "maximum_comb_fraction": 0.85,
        "maximum_multiplier_fraction": 0.85,
        "maximum_ff_fraction": 0.85,
    }
    assert manifest["handoff_tier_order"] == [
        "FULL_PROOF_HMAC",
        "PROOF_EDGE_SHA1",
        "CORE_LITE_R40",
    ]
    assert manifest["synthetic_combined_score_allowed"] is False


def test_decision_classes_and_candidate_paths_are_closed() -> None:
    manifest = load_manifest()
    assert manifest["decision_classes"] == [
        "CONTROL_FAILURE",
        "PROFILE_PRESERVATION_FAILURE",
        "NO_PROFILE_ROUTE_DEPLOYABLE",
        "CORE_LITE_BOARD_HANDOFF_SUPPORTED",
        "PROOF_EDGE_BOARD_HANDOFF_SUPPORTED",
        "FULL_PROOF_BOARD_HANDOFF_SUPPORTED",
        "ROUTABLE_BUT_HEADROOM_NOT_SUPPORTED",
    ]
    paths = manifest["candidate_paths"]
    assert paths == {
        "harnesses": "rtl/cosmic_hw_14_profile_harnesses.v",
        "runner": "benchmarks/cosmic_hw_14_candidate.py",
    }


def test_candidate_files_absent_on_prereg_head() -> None:
    manifest = load_manifest()
    assert manifest["candidate_files_must_be_absent_on_prereg_head"] is True
    for relative in manifest["candidate_paths"].values():
        assert not (ROOT / relative).exists(), relative
