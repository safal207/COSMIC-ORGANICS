from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "cosmic_hw_16_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def test_frozen_parent_and_selected_profile() -> None:
    m = load_manifest()
    assert m["experiment_id"] == "COSMIC-HW-16/v0.1"
    assert m["tracking_issue"] == 115
    assert m["master_issue"] == 103
    assert m["parent"]["source_head"] == "0bbc07d85556a861c9595b869b1f8922e419f0a1"
    assert m["parent"]["decision"] == "PROOF_EDGE_NODSP_BOARD_HANDOFF_SUPPORTED"
    assert m["parent"]["selected_profile"] == "PROOF_EDGE_SHA1_NODSP"
    evidence = m["parent"]["selected_profile_evidence"]
    assert evidence["routes"] == evidence["packs"] == evidence["timing_10mhz_passes"] == 5
    assert evidence["mult18x18d"] == 0
    assert evidence["fmax_min_mhz"] == 18.16


def test_frozen_board_target_and_constraints() -> None:
    m = load_manifest()
    board = m["board"]
    assert board == {
        "name": "ULX3S-85F",
        "fpga": "LFE5U-85F-6BG381C",
        "architecture": "ECP5",
        "density_flag": "--85k",
        "package": "CABGA381",
        "speed_grade": 6,
        "input_clock_mhz": 25.0,
        "processor_clock_mhz": 10.0,
        "primary_usb_connector": "US1",
        "larger_device_fallback_allowed": False,
    }
    c = m["upstream_constraints"]
    assert c["repository"] == "emard/ulx3s"
    assert c["commit"] == "6a92cec6b177191c5b0f80e260013a1f8ec147dd"
    assert c["path"] == "doc/constraints/ulx3s_v20.lpf"
    tokens = "\n".join(c["required_tokens"])
    for token in ("G2", "L4", "M1", "H3", "B2"):
        assert token in tokens


def test_clock_uart_and_handoff_contracts_are_frozen() -> None:
    m = load_manifest()
    clocking = m["clocking"]
    assert clocking["generator"] == "ecppll"
    assert "-i 25 -o 10" in clocking["generator_command"]
    assert clocking["real_clock_domain_required"] is True
    assert clocking["clock_enable_substitute_allowed"] is False
    assert clocking["pll_lock_stable_cycles"] == 16
    assert clocking["expected_pll_parameters"] == {
        "CLKI_DIV": 5,
        "CLKOP_DIV": 60,
        "CLKOP_CPHASE": 30,
        "CLKOP_FPHASE": 0,
        "CLKFB_DIV": 2,
        "FEEDBK_PATH": "CLKOP",
    }

    uart = m["uart"]
    assert uart["baud"] == 115200
    assert uart["format"] == "8N1"
    assert uart["max_absolute_baud_error_fraction"] == 0.02
    assert uart["frame_magic_ascii"] == "CO16"
    assert uart["protocol_version"] == 1
    assert "last_digest" in uart["required_fields"]
    assert "crc32" in uart["required_fields"]

    assert m["placement_seeds"] == [1601, 1602, 1603, 1604, 1605]
    gate = m["route_gate"]
    assert gate["minimum_routes"] == 3
    assert gate["minimum_nonempty_bitstreams"] == 3
    assert gate["minimum_10mhz_processor_timing_passes"] == 3
    assert gate["maximum_comb_fraction"] == gate["maximum_ff_fraction"] == 0.85
    assert gate["required_mult18x18d"] == 0


def test_inherited_rtl_blobs_are_exact() -> None:
    m = load_manifest()
    for relative, expected in m["inherited_source_git_blobs"].items():
        path = ROOT / relative
        assert path.exists(), relative
        assert git_blob_sha(path) == expected, relative


def test_candidate_files_absent_on_prereg_head() -> None:
    m = load_manifest()
    assert m["candidate_files_must_be_absent_on_prereg_head"] is True
    present = [relative for relative in m["candidate_paths"] if (ROOT / relative).exists()]
    assert present == []
