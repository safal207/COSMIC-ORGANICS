from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.cosmic_board_01_oracle import (
    FROZEN_EXPECTED,
    INITIAL_STIMULUS_HEX,
    LFSR_TAPS,
    TICKS,
    build_oracle,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_board_01_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    payload = f"blob {len(data)}\0".encode("ascii") + data
    return hashlib.sha1(payload).hexdigest()


def test_parent_and_selected_profile_are_frozen() -> None:
    manifest = load_manifest()
    assert manifest["experiment_id"] == "COSMIC-BOARD-01A/v0.1"
    assert manifest["tracking_issue"] == 110
    assert manifest["parent"] == {
        "experiment": "COSMIC-HW-15",
        "source_head": "0bbc07d85556a861c9595b869b1f8922e419f0a1",
        "frozen_result_branch": "research/cosmic-hw-15-frozen-result",
        "hosted_run": 32866033513,
        "hosted_job": 97861414261,
        "artifact_id": 9573010882,
        "artifact_digest": "sha256:4805133b1417b1e1e33b19c2247071aa7416cdb0bc9ee303747d8c050952fb3e",
        "decision": "PROOF_EDGE_NODSP_BOARD_HANDOFF_SUPPORTED",
        "selected_profile": "PROOF_EDGE_SHA1_NODSP",
    }
    profile = manifest["selected_profile"]
    assert profile["top_module"] == "cosmic_hw08_sparse_receipt_sha256"
    assert profile["mapping"] == "synth_ecp5 -nodsp"
    assert profile["processing_elements"] == 64
    assert profile["receipt_width_bits"] == 40
    assert profile["receipts_per_commitment"] == 10
    assert profile["sha_engines"] == 1
    assert profile["rtl_edits_allowed"] is False
    assert profile["arithmetic_width_changes_allowed"] is False
    assert profile["pe_count_changes_allowed"] is False
    assert profile["receipt_contract_changes_allowed"] is False
    assert profile["sha_contract_changes_allowed"] is False


def test_inherited_processor_rtl_blobs_are_exact() -> None:
    manifest = load_manifest()
    for relative, expected in manifest["selected_profile"][
        "inherited_source_git_blobs"
    ].items():
        path = ROOT / relative
        assert path.exists(), relative
        assert git_blob_sha(path) == expected, relative


def test_ulx3s_target_clock_and_pin_contract_are_frozen() -> None:
    manifest = load_manifest()
    board = manifest["board"]
    assert board["id"] == "ULX3S_85F"
    assert board["fpga"] == "LFE5U-85F-6BG381C"
    assert board["density_flag"] == "--85k"
    assert board["package"] == "CABGA381"
    assert board["speed_grade"] == 6
    assert board["input_clock_mhz"] == 25.0
    assert board["core_clock_mhz"] == 10.0
    assert board["idcode"] == "0x41113043"
    assert board["uart_baud"] == 115200
    assert board["larger_device_fallback_allowed"] is False
    assert board["different_board_fallback_allowed"] is False

    reference = manifest["official_board_reference"]
    assert reference["repository"] == "emard/ulx3s"
    assert reference["commit"] == "6a92cec6b177191c5b0f80e260013a1f8ec147dd"
    assert reference["constraints_path"] == "doc/constraints/ulx3s_v20.lpf"
    assert reference["constraints_blob"] == "49d246e06c3cdf4b7caae892d2b818786c62de9d"
    assert reference["pins"] == {
        "clk_25mhz": "G2",
        "ftdi_rxd": "L4",
        "ftdi_txd": "M1",
        "btn_reset_start": "R1",
        "led_7": "H3",
        "led_6": "E1",
        "led_5": "E2",
        "led_4": "D1",
        "led_3": "D2",
        "led_2": "C1",
        "led_1": "C2",
        "led_0": "B2",
    }


def test_pll_and_physical_flow_are_frozen_before_candidate() -> None:
    manifest = load_manifest()
    pll = manifest["official_pll_reference"]
    assert pll["repository"] == "YosysHQ/prjtrellis"
    assert pll["commit"] == "3afe7b52b30f4b4417ee98f03016767a502006e3"
    assert pll["example_path"] == "examples/ulx3s/85k.mk"
    assert pll["example_blob"] == "0da6080c6c3462717348219a583b1f088b602d1b"
    assert pll["generator"] == "ecppll"
    assert pll["generator_args"] == [
        "-i",
        "25",
        "-o",
        "10",
        "-n",
        "cosmic_board_01_pll",
        "-f",
        "rtl/cosmic_board_01_pll.v",
    ]
    assert pll["pll_lock_must_gate_reset"] is True
    assert pll["tick_enable_as_clock_substitute_allowed"] is False

    assert manifest["placement_seeds"] == [1601, 1602, 1603, 1604, 1605]
    static = manifest["static_phase"]
    assert static["synthesis"] == "synth_ecp5 -nodsp"
    assert static["place_route"] == (
        "nextpnr-ecp5 --85k --package CABGA381 --speed 6"
    )
    assert static["packer"] == "ecppack --idcode 0x41113043"
    assert static["minimum_successful_routes"] == 3
    assert static["minimum_nonempty_bitstreams"] == 3
    assert static["minimum_10mhz_timing_passes"] == 3
    assert static["maximum_comb_fraction"] == 0.85
    assert static["maximum_ff_fraction"] == 0.85
    assert static["required_mult18x18d"] == 0


def test_workload_and_uart_protocol_are_exact_before_candidate() -> None:
    manifest = load_manifest()
    workload = manifest["static_workload"]
    assert workload["accepted_ticks"] == TICKS == 64
    assert workload["stimulus_bits"] == 512
    assert workload["initial_stimulus_hex"] == INITIAL_STIMULUS_HEX
    assert workload["feedback_taps"] == list(LFSR_TAPS)
    assert workload["explicit_final_flush"] is True
    assert workload["uart_format"] == "115200-8N1"
    assert workload["host_timing_may_change_sequence"] is False
    assert workload["oracle_path"] == "benchmarks/cosmic_board_01_oracle.py"

    oracle = build_oracle()
    summary = oracle["summary"]
    for key, expected in FROZEN_EXPECTED.items():
        assert summary[key] == expected, key
        assert workload.get(key, expected) == expected, key

    protocol = manifest["uart_protocol"]
    assert protocol["sync_hex"] == "434f"
    assert protocol["crc"] == {
        "name": "CRC-16/CCITT-FALSE",
        "polynomial_hex": "1021",
        "initial_hex": "ffff",
        "reflection": False,
        "xorout_hex": "0000",
        "coverage": "type || payload_length || record_sequence || payload",
    }
    assert protocol["wire_order"] == (
        "START, DIGEST records in commitment-sequence order, END"
    )
    assert protocol["frame_types"]["START"]["payload_length"] == 12
    assert protocol["frame_types"]["DIGEST"]["expected_count"] == 277
    assert protocol["frame_types"]["END"]["payload_length"] == 49
    assert protocol["expected_frame_count"] == summary["uart_frame_count"]
    assert protocol["expected_transcript_bytes"] == summary[
        "uart_transcript_bytes"
    ]
    assert protocol["expected_transcript_sha256"] == summary[
        "uart_transcript_sha256"
    ]
    assert protocol["truncated_or_malformed_transcript_fails_closed"] is True


def test_static_and_physical_claims_are_separated() -> None:
    manifest = load_manifest()
    physical = manifest["physical_phase"]
    assert physical["starts_only_after_static_green"] is True
    assert physical["requires_actual_board"] is True
    assert physical["minimum_cold_runs"] == 3
    assert physical["exact_oracle_equality_required"] is True
    assert physical["truncated_uart_fails_closed"] is True
    assert physical["power_measurement_required"] is False

    assert "ULX3S_STATIC_BITSTREAM_SUPPORTED" in manifest["decision_classes"]
    assert "COSMIC_PROOF_EDGE_HIL_SUPPORTED" in manifest["decision_classes"]
    assert manifest["expected_answer_rom_allowed"] is False
    assert manifest["checksum_feedback_allowed"] is False
    assert manifest["synthetic_combined_score_allowed"] is False
    assert "exact workload" in manifest["stop_rule"]
    assert "UART protocol" in manifest["stop_rule"]


def test_candidate_files_absent_on_prereg_head() -> None:
    manifest = load_manifest()
    assert manifest["candidate_files_must_be_absent_on_prereg_head"] is True
    for relative in manifest["candidate_paths"].values():
        assert not (ROOT / relative).exists(), relative
