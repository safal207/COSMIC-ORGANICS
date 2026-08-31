from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools.cosmic_hw_21_network import (
    EXPECTED_LAST_DIGEST,
    EXPECTED_PARENT_HEAD,
    EXPECTED_PARENT_TREE,
    LAYERS,
    load_manifest,
    make_testbench,
    simulate_layer,
)


ROOT = Path(__file__).resolve().parents[1]
RTL_PATH = ROOT / "rtl" / "cosmic_hw_21_network_pyramid.v"


def test_manifest_freezes_exact_hw20_evidence() -> None:
    manifest = load_manifest()
    parent = manifest["parent"]
    assert parent["source_head"] == EXPECTED_PARENT_HEAD
    assert parent["source_tree"] == EXPECTED_PARENT_TREE
    assert parent["x1_compute_cycles"] == 862
    assert parent["x2_compute_cycles"] == 482
    assert parent["artifact_id"] == 9735549367
    assert parent["physical_hil_state"] == "NOT_RUN"
    assert manifest["workload"]["last_digest"] == EXPECTED_LAST_DIGEST


def test_network_layers_double_without_superlinear_claim() -> None:
    manifest = load_manifest()
    assert tuple(manifest["network_pyramid"]["layers"]) == LAYERS
    assert LAYERS == (2, 4, 8, 16)
    assert all(right == left * 2 for left, right in zip(LAYERS, LAYERS[1:]))
    assert manifest["network_pyramid"]["superlinear_speedup_claim_allowed"] is False
    assert manifest["workload"]["receipt_output_lanes"] == 1
    assert manifest["workload"]["aggregate_sha_busy_cycles"] == 832


def test_rtl_has_all_bounded_layers_and_no_oracle() -> None:
    text = RTL_PATH.read_text(encoding="utf-8")
    assert "module cosmic_hw21_network_pyramid" in text
    for engines in LAYERS:
        assert f"module cosmic_hw21_network_pyramid_x{engines}" in text
        assert f"#(.ENGINES({engines}))" in text
    assert "next_retire_sequence" in text
    assert "waiting_valid" in text
    assert EXPECTED_LAST_DIGEST not in text.lower()


def test_generated_testbench_preserves_exact_work_and_stimulus() -> None:
    text = make_testbench(8)
    assert "localparam integer ENGINES = 8;" in text
    assert ".stimulus_bus({64{8'h64}})" in text
    assert "aggregate_busy_cycles != 832" in text
    assert EXPECTED_LAST_DIGEST in text.lower()


def test_candidate_paths_are_bounded() -> None:
    assert set(load_manifest()["candidate_paths"]) == {
        ".github/workflows/cosmic_hw_21_network_contract.yml",
        "benchmarks/cosmic_hw_21_network_manifest.json",
        "docs/cosmic-hw-21-network-pyramid.md",
        "rtl/cosmic_hw_21_network_pyramid.v",
        "tests/test_cosmic_hw_21_network.py",
        "tools/cosmic_hw_21_network.py",
    }


def test_x2_cycle_control_and_work_conservation(tmp_path: Path) -> None:
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        pytest.skip("cycle-accurate simulator unavailable; HW-21 CI installs it")
    result = simulate_layer(tmp_path, 2, load_manifest())
    assert result["compute_cycles"] == 482
    assert result["aggregate_sha_busy_cycles"] == 832
    assert result["oracle_match"] is True
    assert result["last_digest"] == EXPECTED_LAST_DIGEST
    assert result["speedup_vs_x1"] <= 2.0


def test_direct_entrypoint_is_runnable() -> None:
    process = subprocess.run(
        [sys.executable, "tools/cosmic_hw_21_network.py", "--help"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.returncode == 0, process.stdout
    assert "1+1=N SHA network-pyramid" in process.stdout
