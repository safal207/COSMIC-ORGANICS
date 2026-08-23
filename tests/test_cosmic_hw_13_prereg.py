from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "cosmic_hw_13_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_exact_parent_and_protocol() -> None:
    m = load_manifest()
    assert m["experiment_id"] == "COSMIC-HW-13/v0.1"
    assert m["parent_hw12_source_head"] == "7bad7ba095c65221e057696df40fcd6c53dee2b8"
    assert m["parent_system"] == "B1_M2_HMACx1"


def test_exact_physical_target_is_frozen() -> None:
    t = load_manifest()["target"]
    assert t == {
        "vendor": "Lattice",
        "family": "ECP5",
        "part": "LFE5U-85F-8BG381C",
        "nextpnr_density_flag": "--85k",
        "package": "CABGA381",
        "speed_grade": "8",
        "requested_clock_mhz": 10.0,
    }


def test_exact_toolchain_versions_are_frozen() -> None:
    t = load_manifest()["toolchain"]
    assert t["runner"] == "ubuntu-24.04"
    assert t["yosys_apt_version"] == "0.33-5build2"
    assert t["iverilog_apt_version"] == "12.0-2build2"
    assert t["nextpnr_ecp5_apt_version"] == "0.6-3build5"
    assert t["fpga_trellis_apt_version"] == "1.4-2build4"
    assert t["synthesis_command_family"] == "synth_ecp5"
    assert t["packer"] == "ecppack"


def test_harness_contract_is_narrow_and_nonconstant() -> None:
    h = load_manifest()["physical_harness"]
    assert h["top"] == "cosmic_hw13_ecp5_harness"
    assert h["exact_core_module"] == "cosmic_hw12_b1_m2_hmacx1"
    assert h["external_ports"] == ["clk", "reset", "status[7:0]"]
    assert h["external_pin_count"] == 10
    assert h["stimulus_state_bits"] == 512
    for key in (
        "stimulus_must_be_dynamic",
        "flush_must_be_dynamic",
        "tree_flush_must_be_dynamic",
        "source_sequence_must_be_dynamic",
        "sink_ready_must_be_dynamic",
        "all_major_outputs_must_feed_observable_checksum",
    ):
        assert h[key] is True
    assert h["checksum_feedback_to_core_allowed"] is False
    assert h["expected_answer_rom_allowed"] is False


def test_seed_and_decision_policy_is_frozen() -> None:
    m = load_manifest()
    p = m["placement"]
    assert p["seeds"] == [1301, 1302, 1303, 1304, 1305]
    assert p["required_successful_routes"] == 3
    assert p["required_10mhz_passes"] == 3
    assert p["report_all_seeds"] is True
    assert p["best_seed_only_reporting_allowed"] is False
    a = m["anti_pruning_gate"]
    assert a["min_harness_lut_fraction_of_core_only"] == 0.98
    assert a["min_harness_ff_fraction_of_core_only"] == 0.98
    assert a["min_harness_multiplier_fraction_of_core_only"] == 1.0
    assert m["larger_fpga_fallback_allowed_in_hw13"] is False
    assert m["synthetic_combined_score_allowed"] is False


def test_inherited_hmac_oracle_is_frozen() -> None:
    f = load_manifest()["functional_gates"]
    assert f["rerun_hw12_prereg"] is True
    assert f["rerun_hmac_kat_vectors"] == 446
    assert f["hmac_frozen_root_vectors"] == 444
    assert f["hmac_oracle_fingerprint"] == "3b3f577479cf42343196ce1245024c38f3a3209ff18bd2e157ce761e60096885"
    assert f["harness_smoke_required"] is True


def test_candidate_files_absent_on_prereg_head() -> None:
    paths = load_manifest()["candidate_paths"]
    assert not (ROOT / paths["harness_rtl"]).exists()
    assert not (ROOT / paths["candidate_runner"]).exists()
