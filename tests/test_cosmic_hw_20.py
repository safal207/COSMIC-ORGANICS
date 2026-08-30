from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools.cosmic_hw_20_stretcher import (
    EXPECTED_LAST_DIGEST,
    EXPECTED_PARENT_HEAD,
    EXPECTED_PARENT_TREE,
    classify,
    load_manifest,
    simulate_candidate,
)


ROOT = Path(__file__).resolve().parents[1]
RTL_PATH = ROOT / "rtl" / "cosmic_hw_20_stretcher_top.v"


def test_manifest_freezes_exact_hw19_parent_and_oracle() -> None:
    manifest = load_manifest()
    assert manifest["parent"]["source_head"] == EXPECTED_PARENT_HEAD
    assert manifest["parent"]["source_tree"] == EXPECTED_PARENT_TREE
    assert manifest["parent"]["physical_hil_state"] == "NOT_RUN"
    assert manifest["parent"]["single_sha_compute_cycles"] == 862
    assert manifest["workload"]["last_digest"] == EXPECTED_LAST_DIGEST
    assert manifest["workload"]["ordered_receipts"] == 128
    assert manifest["workload"]["sha256_digests"] == 13


def test_stretcher_is_two_engines_plus_noncomputing_waiting_slot() -> None:
    manifest = load_manifest()
    architecture = manifest["stretcher_architecture"]
    assert architecture["physical_sha256_engines"] == 2
    assert architecture["complete_waiting_blocks"] == 1
    assert architecture["currently_filling_messages"] == 1
    assert architecture["virtual_third_slot_is_compute_engine"] is False
    assert architecture["drop_allowed"] is False
    assert architecture["unbounded_queue_allowed"] is False
    gates = manifest["cycle_gates"]
    assert gates["maximum_honest_speedup"] == 2.0
    assert gates["two_engine_sha_round_lower_bound_cycles"] == 448


def test_rtl_instantiates_exactly_the_inherited_x2_wrapper() -> None:
    text = RTL_PATH.read_text(encoding="utf-8")
    assert "cosmic_hw09_sparse_receipt_sha256x2 processor" in text
    assert "cosmic_hw09_sparse_receipt_sha256x4" not in text
    assert "virtual carrier" in text
    assert "expected_digest" not in text.lower()
    assert EXPECTED_LAST_DIGEST not in text.lower()


def test_candidate_paths_are_bounded() -> None:
    assert set(load_manifest()["candidate_paths"]) == {
        ".github/workflows/cosmic_hw_20_stretcher_contract.yml",
        "benchmarks/cosmic_hw_20_manifest.json",
        "docs/cosmic-hw-20-stretcher.md",
        "rtl/cosmic_hw_20_stretcher_top.v",
        "tests/test_cosmic_hw_20.py",
        "tools/cosmic_hw_20_stretcher.py",
    }


def test_decision_keeps_cycle_value_separate_from_cpu_parity() -> None:
    manifest = load_manifest()
    simulation = {"compute_cycles": 450}
    board = {"trellis_comb": 80_000}
    assert (
        classify(manifest, simulation, board, None)
        == "STRETCHER_VALUE_SUPPORTED_CPU_PARITY_NOT_REACHED"
    )
    simulation["compute_cycles"] = 113
    assert (
        classify(manifest, simulation, board, None)
        == "STRETCHER_CPU_PARITY_MODELED_PHYSICAL_NOT_RUN"
    )
    board["trellis_comb"] = 83_641
    assert classify(manifest, simulation, board, None) == "ECP5_CAPACITY_FAILURE"


def test_cycle_accurate_stretcher_uses_both_engines_and_queue(tmp_path: Path) -> None:
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        pytest.skip("cycle-accurate simulator unavailable; HW-20 CI installs it")
    result = simulate_candidate(tmp_path, load_manifest())
    assert result["oracle_match"] is True
    assert result["last_digest"] == EXPECTED_LAST_DIGEST
    assert 448 <= result["compute_cycles"] < 862
    assert 1.0 < result["cycle_speedup"] <= 2.0
    assert sum(result["per_engine_blocks_accepted"]) == 13
    assert min(result["per_engine_blocks_accepted"]) > 0
    assert result["both_engines_busy_cycles"] > 0
    assert result["both_engines_busy_with_waiting_block_cycles"] > 0
    assert result["virtual_third_slot_compute_engines"] == 0


def test_direct_entrypoint_is_runnable() -> None:
    process = subprocess.run(
        [sys.executable, "tools/cosmic_hw_20_stretcher.py", "--help"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.returncode == 0, process.stdout
    assert "two-engine plus waiting-slot stretcher" in process.stdout
