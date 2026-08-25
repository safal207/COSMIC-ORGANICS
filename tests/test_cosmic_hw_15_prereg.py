from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_15_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = f"blob {len(data)}\0".encode("ascii") + data
    return hashlib.sha1(payload).hexdigest()


def test_identity_parent_and_frozen_result() -> None:
    manifest = load_manifest()
    assert manifest["experiment_id"] == "COSMIC-HW-15/v0.1"
    assert manifest["tracking_issue"] == 105
    assert manifest["parent"] == {
        "experiment": "COSMIC-HW-14",
        "source_head": "292b94bd3e1c58355439c9212a7af5fa08c08a99",
        "hosted_run": 32860108267,
        "hosted_job": 97841692462,
        "artifact_id": 9569132521,
        "artifact_digest": "sha256:f8ff293c1d9a056b097c046a227e0097783d7f9247744042b229e53f355dad0f",
        "decision": "NO_PROFILE_ROUTE_DEPLOYABLE",
    }
    assert manifest["frozen_full_profile_control"] == {
        "id": "FULL_PROOF_HMAC",
        "trellis_comb": 116755,
        "trellis_ff": 29503,
        "mult18x18d": 201,
        "successful_routes": 0,
        "candidate_in_hw15": False,
    }


def test_target_toolchain_seeds_and_mapping_are_frozen() -> None:
    manifest = load_manifest()
    target = manifest["target"]
    assert target["device"] == "LFE5U-85F-8BG381C"
    assert target["density_flag"] == "--85k"
    assert target["package"] == "CABGA381"
    assert target["speed_grade"] == 8
    assert target["requested_clock_mhz"] == 10.0
    assert target["synthesis_control"] == "synth_ecp5"
    assert target["synthesis_candidate"] == "synth_ecp5 -nodsp"
    assert target["larger_device_fallback_allowed"] is False

    assert manifest["placement_seeds"] == [1501, 1502, 1503, 1504, 1505]
    assert manifest["device_capacity"] == {
        "trellis_comb": 83640,
        "trellis_ff": 83640,
        "mult18x18d": 156,
        "dp16kd": 208,
    }
    assert manifest["mapping_intervention"] == {
        "candidate_flag": "-nodsp",
        "rtl_edits_allowed": False,
        "manual_primitive_replacement_allowed": False,
        "changed_arithmetic_widths_allowed": False,
        "candidate_mult18x18d_required": 0,
    }


def test_profiles_controls_and_selection_rule_are_frozen() -> None:
    manifest = load_manifest()
    profiles = {row["id"]: row for row in manifest["profiles"]}
    assert set(profiles) == {"CORE_LITE_R40_NODSP", "PROOF_EDGE_SHA1_NODSP"}

    core = profiles["CORE_LITE_R40_NODSP"]
    assert core["tier"] == 1
    assert core["top_module"] == "cosmic_hw07_mesh64_receipt"
    assert core["harness_top"] == "cosmic_hw14_core_lite_harness"
    assert core["parameters"] == {"SPARSE": 1, "FIFO_DEPTH": 4}
    assert core["auto_dsp_control_yosys"] == {
        "trellis_comb": 27017,
        "trellis_ff": 5027,
        "mult18x18d": 236,
    }

    proof = profiles["PROOF_EDGE_SHA1_NODSP"]
    assert proof["tier"] == 2
    assert proof["top_module"] == "cosmic_hw08_sparse_receipt_sha256"
    assert proof["harness_top"] == "cosmic_hw14_proof_edge_harness"
    assert proof["parameters"] == {}
    assert proof["auto_dsp_control_yosys"] == {
        "trellis_comb": 38123,
        "trellis_ff": 8507,
        "mult18x18d": 165,
    }

    assert manifest["handoff_tier_order"] == [
        "PROOF_EDGE_SHA1_NODSP",
        "CORE_LITE_R40_NODSP",
    ]
    assert manifest["route_deployable_gate"] == {
        "minimum_successful_routes": 3,
        "minimum_nonempty_bitstreams": 3,
        "minimum_10mhz_timing_passes": 3,
        "frozen_seed_count": 5,
    }
    assert manifest["board_handoff_headroom"] == {
        "maximum_comb_fraction": 0.85,
        "maximum_ff_fraction": 0.85,
        "required_mult18x18d_fraction": 0.0,
    }
    assert manifest["synthetic_combined_score_allowed"] is False


def test_inherited_sources_and_exact_harness_instances_are_frozen() -> None:
    manifest = load_manifest()
    for relative, expected in manifest["inherited_source_git_blobs"].items():
        path = ROOT / relative
        assert path.exists(), relative
        assert git_blob_sha(path) == expected, relative

    harness = (ROOT / "rtl" / "cosmic_hw_14_profile_harnesses.v").read_text(
        encoding="utf-8"
    )
    assert "module cosmic_hw14_core_lite_harness" in harness
    assert (
        "cosmic_hw07_mesh64_receipt #(.SPARSE(1), .FIFO_DEPTH(4)) profile"
        in harness
    )
    assert "module cosmic_hw14_proof_edge_harness" in harness
    assert "cosmic_hw08_sparse_receipt_sha256 profile" in harness
    assert "observation_word" in harness
    assert "checksum" in harness


def test_toolchain_and_anti_pruning_gates_are_explicit() -> None:
    manifest = load_manifest()
    assert manifest["toolchain_prereg_gate"] == {
        "help_must_expose_nodsp": True,
        "toy_default_must_infer_dsp": True,
        "toy_nodsp_must_infer_zero_dsp": True,
        "toy_nodsp_route_pack_at_10mhz": True,
    }
    assert manifest["anti_pruning_gate"] == {
        "minimum_harness_comb_fraction_of_core": 0.98,
        "minimum_harness_ff_fraction_of_core": 0.98,
        "zero_over_zero_is_neutral": True,
        "exact_profile_instance_required": True,
        "inherited_source_blob_match_required": True,
    }


def test_candidate_files_absent_on_prereg_head() -> None:
    manifest = load_manifest()
    assert manifest["candidate_files_must_be_absent_on_prereg_head"] is True
    for relative in manifest["candidate_paths"].values():
        assert not (ROOT / relative).exists(), relative


def test_decision_classes_and_stop_rule_are_frozen() -> None:
    manifest = load_manifest()
    assert manifest["decision_classes"] == [
        "CONTROL_FAILURE",
        "NODSP_SEMANTIC_FAILURE",
        "NODSP_MAPPING_FAILURE",
        "NO_NODSP_PROFILE_ROUTE_DEPLOYABLE",
        "CORE_LITE_NODSP_BOARD_HANDOFF_SUPPORTED",
        "PROOF_EDGE_NODSP_BOARD_HANDOFF_SUPPORTED",
        "NODSP_ROUTABLE_BUT_HEADROOM_NOT_SUPPORTED",
    ]
    assert "do not alter RTL arithmetic" in manifest["stop_rule"]
    assert "later board experiment only" in manifest["claim_boundary"]
