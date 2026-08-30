from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest

from tools.cosmic_hw_19_compare import (
    EXPECTED_LAST_DIGEST,
    EXPECTED_PARENT_HEAD,
    load_manifest,
    simulate_hardware_model,
)
from tools.cosmic_hw_19_remote_run import archive_evidence, load_config


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_19_manifest.json"


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def test_manifest_freezes_parent_workload_and_not_run_boundary() -> None:
    manifest = load_manifest()
    assert manifest["parent"]["source_head"] == EXPECTED_PARENT_HEAD
    assert manifest["parent"]["physical_hil_state"] == "NOT_RUN"
    assert manifest["workload"] == {
        "operation_name": "ULX3S_PROOF_EDGE_A_M_C_2TICK",
        "sites": 64,
        "accepted_ticks": 2,
        "stimulus_s100": 100,
        "initial_phase": "A",
        "final_phase": "C",
        "ordered_receipts": 128,
        "full_commitment_batches": 12,
        "partial_commitment_receipts": 8,
        "sha256_digests": 13,
        "last_digest": EXPECTED_LAST_DIGEST,
        "frame_sha256": "16d448b3c5af0a09edc1817c6cf980f12d4806f0b6cfe969b2b524538e7e799b",
    }


def test_cpu_protocol_is_single_threaded_and_statistical() -> None:
    cpu = load_manifest()["cpu_baseline"]
    assert cpu["threads"] == 1
    assert cpu["samples"] == 31
    assert cpu["warmup_iterations"] == 2000
    assert cpu["timed_iterations_per_sample"] == 20000
    assert cpu["single_operation_latency_samples"] == 10000
    assert "p99_single_operation_ns" in cpu["reported_statistics"]
    assert "-O3" in cpu["compiler_flags"]
    assert "-march=native" in cpu["compiler_flags"]


def test_inherited_blobs_and_candidate_paths_are_exact() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for relative, expected in manifest["inherited_source_blobs"].items():
        assert git_blob_sha(ROOT / relative) == expected
    assert set(manifest["candidate_paths"]) == {
        ".gitignore",
        ".github/workflows/ci.yml",
        ".github/workflows/cosmic_hw_19_no_purchase_contract.yml",
        "benchmarks/cosmic_hw_19_cpu.cpp",
        "benchmarks/cosmic_hw_19_manifest.json",
        "tools/cosmic_hw_19_compare.py",
        "tools/cosmic_hw_19_remote_run.py",
        "tests/test_cosmic_hw_19.py",
        "docs/cosmic-hw-19-no-purchase.md",
        "docs/cosmic-hw-19-operator.example.json",
    }


def test_claim_boundary_forbids_modeled_superiority() -> None:
    manifest = load_manifest()
    boundary = manifest["claim_boundary"]
    assert "non-physical FPGA latency model" in boundary
    assert "CPU superiority" in boundary
    assert "FPGA superiority" in boundary
    assert manifest["hardware_model"]["routed_fmax_is_measured_board_clock"] is False


def test_cycle_accurate_model_matches_exact_oracle(tmp_path: Path) -> None:
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        pytest.skip("cycle-accurate simulator unavailable; CI installs and requires it")
    result = simulate_hardware_model(tmp_path, load_manifest())
    assert result["oracle_match"] is True
    assert result["compute_cycles"] > 0
    assert result["last_digest"] == EXPECTED_LAST_DIGEST
    assert result["physical_execution_state"] == "NOT_RUN"
    assert all(
        point["physical_measurement"] is False
        for point in result["modeled_points"].values()
    )


def test_cpp_baseline_compiles_and_matches_oracle(tmp_path: Path) -> None:
    executable = tmp_path / "cpu"
    compile_process = subprocess.run(
        [
            "g++",
            "-O3",
            "-DNDEBUG",
            "-std=c++20",
            "-march=native",
            "-Wno-deprecated-declarations",
            "benchmarks/cosmic_hw_19_cpu.cpp",
            "-lcrypto",
            "-o",
            str(executable),
        ],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert compile_process.returncode == 0, compile_process.stdout
    run_process = subprocess.run(
        [str(executable), "100", "3", "10", "100"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert run_process.returncode == 0, run_process.stdout
    result = json.loads(run_process.stdout)
    assert result["oracle_match"] is True
    assert result["last_digest"] == EXPECTED_LAST_DIGEST
    assert result["mean_ns_per_operation"] > 0
    assert result["p99_single_operation_ns"] > 0
    assert result["runtime_input_source"] == "volatile int8_t"


def valid_config(tmp_path: Path) -> dict[str, object]:
    return {
        "bitstream": str(tmp_path / "subject.bit"),
        "serial_port": "/dev/serial/by-id/test",
        "programmer": "openFPGALoader",
        "power_cycle_hook": str(tmp_path / "power-cycle"),
        "output_dir": str(tmp_path / "evidence"),
        "media": [str(tmp_path / "photo.jpg")],
        "operator": "Test Operator",
        "board_id": "BOARD-1",
        "board_revision": "3.0.8",
        "fpga_marking": "LFE5U-85F-6BG381C",
        "confirm_volatile_sram_programming": True,
    }


def test_remote_config_is_fail_closed(tmp_path: Path) -> None:
    config = valid_config(tmp_path)
    path = tmp_path / "operator.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    args = load_config(path)
    assert isinstance(args, argparse.Namespace)
    assert args.confirm_volatile_sram_programming is True

    config["confirm_volatile_sram_programming"] = False
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="volatile SRAM"):
        load_config(path)

    config = valid_config(tmp_path)
    config["unexpected"] = "unsafe"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected"):
        load_config(path)


def test_evidence_archive_has_digest_and_refuses_overwrite(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "cosmic_hw_18_result.json").write_text("{}\n", encoding="utf-8")
    record = archive_evidence(evidence)
    archive = Path(record["path"])
    assert archive.is_file()
    assert record["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert Path(record["sha256_file"]).is_file()
    with tarfile.open(archive, "r:gz") as handle:
        assert handle.getnames() == ["evidence", "evidence/cosmic_hw_18_result.json"]
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        archive_evidence(evidence)


@pytest.mark.parametrize(
    "script,marker",
    [
        ("tools/cosmic_hw_19_compare.py", "HW-19"),
        ("tools/cosmic_hw_19_remote_run.py", "remote-operator"),
    ],
)
def test_direct_entrypoints_are_runnable(script: str, marker: str) -> None:
    process = subprocess.run(
        [sys.executable, script, "--help"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.returncode == 0, process.stdout
    assert marker in process.stdout
