from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from tools.cosmic_hw_16_uart_verify import build_expected_frame
from tools.cosmic_hw_18_hil import (
    EXPECTED_BITSTREAM_BYTES,
    EXPECTED_BITSTREAM_SHA256,
    EXPECTED_PARENT_HEAD,
    capture_uart,
    classify_failure,
    configure_serial,
    extract_frame,
    inventory_tree,
    load_manifest,
    run_hil,
    verify_bitstream,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_18_manifest.json"


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def test_parent_subject_and_physical_question_are_exact() -> None:
    manifest = load_manifest()
    assert manifest["experiment_id"] == "COSMIC-HW-18/v0.1"
    assert manifest["protocol"] == "COSMIC-HW-18-HIL/v0.1"
    assert manifest["parent"] == {
        "repository": "safal207/COSMIC-ORGANICS",
        "pull_request": 120,
        "source_head": EXPECTED_PARENT_HEAD,
        "source_tree": "3f0ea3940ed87ba4fa671915a64ad4f8e8f142b3",
        "workflow_run": 33313877706,
        "run_attempt": 1,
        "decision": "ULX3S_EXTENDED_BUDGET_BITSTREAM_READY",
        "artifact_id": 9733436976,
        "artifact_digest": (
            "sha256:73b829eb86eaf6872cdba532d7c31816010cf50b56490d47ef9a0927e7501e60"
        ),
        "canonical_seed": 1601,
        "canonical_bitstream_bytes": EXPECTED_BITSTREAM_BYTES,
        "canonical_bitstream_sha256": EXPECTED_BITSTREAM_SHA256,
        "board_netlist_sha256": "50fc484a52d890ad959e72969d656d207f6c8f9ecd1e504d4e4f0281c2803215",
    }
    assert "ten externally power-cycled cold repetitions" in manifest["question"]


def test_programming_is_volatile_and_gate_is_fail_closed() -> None:
    manifest = load_manifest()
    programming = manifest["programming"]
    gate = manifest["physical_hil_gate"]
    assert programming["volatile_sram_only"] is True
    assert programming["persistent_flash_allowed"] is False
    assert programming["power_cycle_hook_required"] is True
    assert programming["allowed_programmers"] == {
        "openFPGALoader": ["openFPGALoader", "-b", "ulx3s", "{bitstream}"],
        "fujprog": ["fujprog", "{bitstream}"],
    }
    assert gate["cold_repetitions"] == 10
    assert gate["all_repetitions_required"] is True
    assert gate["clean_harness_worktree_required"] is True
    assert gate["photo_or_video_required"] is True
    assert all(gate.values())


def test_uart_oracle_is_frozen() -> None:
    manifest = load_manifest()
    uart = manifest["frozen_uart"]
    frame = build_expected_frame()
    assert uart["baud"] == 115200
    assert uart["format"] == "8N1"
    assert uart["frame_bytes"] == 60
    assert uart["magic_ascii"] == "CO16"
    assert uart["frame_sha256"] == hashlib.sha256(frame).hexdigest()
    assert uart["accepted_tick_count"] == 2
    assert uart["receipt_count"] == 128
    assert uart["digest_count"] == 13
    assert uart["error_flags"] == 0


def test_extract_frame_is_magic_aligned_and_complete() -> None:
    frame = build_expected_frame()
    assert extract_frame(frame) == frame
    assert extract_frame(b"noise" + frame) == frame
    assert extract_frame(frame[:-1]) is None
    assert extract_frame(b"CO15" + frame[4:]) is None


def test_posix_uart_capture_accepts_prefixed_complete_frame() -> None:
    master_fd, slave_fd = os.openpty()
    frame = build_expected_frame()
    sender: threading.Thread | None = None
    try:
        configure_serial(slave_fd, 115200)

        def send_frame() -> None:
            time.sleep(0.02)
            os.write(master_fd, b"startup-noise" + frame)

        sender = threading.Thread(target=send_frame)
        sender.start()
        raw, observed = capture_uart(slave_fd, 1)
        sender.join(timeout=1)
    finally:
        os.close(master_fd)
        os.close(slave_fd)
    assert sender is not None and not sender.is_alive()
    assert observed == frame
    assert raw.endswith(frame)


def test_bitstream_verification_rejects_wrong_subject(tmp_path: Path) -> None:
    manifest = load_manifest()
    wrong = tmp_path / "wrong.bit"
    wrong.write_bytes(b"not-the-canonical-bitstream")
    result = verify_bitstream(wrong, manifest)
    assert result["passed"] is False
    assert result["sha256_match"] is False
    assert result["size_match"] is False


def test_inventory_covers_hook_files_and_rejects_symlinks(tmp_path: Path) -> None:
    repetition = tmp_path / "repetition-01"
    repetition.mkdir()
    hook_evidence = repetition / "relay_readback.json"
    hook_evidence.write_text('{"power_removed": true}\n', encoding="utf-8")
    subject_dir = tmp_path / "subject"
    subject_dir.mkdir()
    subject = subject_dir / "cosmic_hw_17_canonical.bit"
    subject.write_bytes(b"subject")
    records = inventory_tree(tmp_path)
    assert records == [
        {
            "path": "repetition-01/relay_readback.json",
            "role": "power_cycle_hook_evidence",
            "bytes": hook_evidence.stat().st_size,
            "sha256": hashlib.sha256(hook_evidence.read_bytes()).hexdigest(),
        },
        {
            "path": "subject/cosmic_hw_17_canonical.bit",
            "role": "canonical_bitstream_subject",
            "bytes": subject.stat().st_size,
            "sha256": hashlib.sha256(subject.read_bytes()).hexdigest(),
        },
    ]

    link = repetition / "forbidden-link"
    link.symlink_to(hook_evidence)
    with pytest.raises(RuntimeError, match="symlink is forbidden"):
        inventory_tree(tmp_path)


@pytest.mark.parametrize(
    ("stage", "decision"),
    [
        ("power_cycle", "POWER_CYCLE_FAILURE"),
        ("serial", "BOARD_NOT_AVAILABLE"),
        ("programming", "PROGRAMMING_FAILURE"),
        ("uart", "UART_PROTOCOL_FAILURE"),
        ("oracle", "BOARD_ORACLE_MISMATCH"),
        ("evidence", "EVIDENCE_INCOMPLETE"),
        ("unknown", "EVIDENCE_INCOMPLETE"),
    ],
)
def test_failure_classification_never_becomes_green(stage: str, decision: str) -> None:
    assert classify_failure(stage) == decision
    assert decision != "ULX3S_PROOF_EDGE_HIL_SUPPORTED"


def test_inherited_verifier_blob_and_candidate_paths() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for relative, expected in manifest["inherited_source_blobs"].items():
        assert git_blob_sha(ROOT / relative) == expected
    assert set(manifest["candidate_paths"]) == {
        ".github/workflows/cosmic_hw_18_hil_contract.yml",
        "benchmarks/cosmic_hw_18_manifest.json",
        "tools/cosmic_hw_18_hil.py",
        "tests/test_cosmic_hw_18_hil.py",
        "docs/cosmic-hw-18-physical-hil.md",
    }


def test_claim_boundary_does_not_promote_hil_to_cpu_superiority() -> None:
    boundary = load_manifest()["claim_boundary"]
    assert "one identified physical ULX3S-85F board" in boundary
    assert "CPU/GPU superiority" in boundary
    assert "measured power or energy" in boundary


def test_direct_script_entrypoint_is_runnable() -> None:
    process = subprocess.run(
        [sys.executable, "tools/cosmic_hw_18_hil.py", "--help"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.returncode == 0, process.stdout
    assert "COSMIC-HW-18" in process.stdout


def test_success_path_requires_and_records_all_ten_repetitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    master_fd, slave_fd = os.openpty()
    bitstream = tmp_path / "input.bit"
    bitstream.write_bytes(b"test-subject")
    media = tmp_path / "rig-photo.jpg"
    media.write_bytes(b"test-photo")
    output_dir = tmp_path / "evidence"
    frame = build_expected_frame()

    monkeypatch.setattr(
        "tools.cosmic_hw_18_hil.git_identity",
        lambda: {
            "repository_root": str(ROOT),
            "head": "a" * 40,
            "tree": "b" * 40,
            "branch": "test",
            "clean": True,
            "status": [],
        },
    )
    monkeypatch.setattr(
        "tools.cosmic_hw_18_hil.verify_bitstream",
        lambda path, manifest: {
            "path": str(Path(path).resolve()),
            "bytes": Path(path).stat().st_size,
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "size_match": True,
            "sha256_match": True,
            "passed": True,
        },
    )
    monkeypatch.setattr(
        "tools.cosmic_hw_18_hil.resolve_executable", lambda value: Path("/bin/true")
    )
    monkeypatch.setattr(
        "tools.cosmic_hw_18_hil.build_programmer_command",
        lambda manifest, programmer, path: (
            Path("/bin/true"),
            ["programmer", str(path)],
        ),
    )

    def fake_run_process(command: list[str], timeout: int) -> dict:
        if command[0] == "programmer":
            os.write(master_fd, b"startup-noise" + frame)
        return {
            "command": command,
            "started_at": "2026-08-30T00:00:00Z",
            "completed_at": "2026-08-30T00:00:01Z",
            "runtime_seconds": 1.0,
            "returncode": 0,
            "timed_out": False,
            "output": "ok\n",
            "passed": True,
        }

    monkeypatch.setattr("tools.cosmic_hw_18_hil.run_process", fake_run_process)
    args = type(
        "Args",
        (),
        {
            "confirm_volatile_sram_programming": True,
            "operator": "Test Operator",
            "board_id": "TEST-BOARD-1",
            "board_revision": "3.0.8",
            "fpga_marking": "LFE5U-85F-6BG381C",
            "bitstream": bitstream,
            "power_cycle_hook": Path("/bin/true"),
            "programmer": "openFPGALoader",
            "serial_port": Path(os.ttyname(slave_fd)),
            "media": [media],
            "output_dir": output_dir,
        },
    )()
    try:
        result = run_hil(args)
    finally:
        os.close(master_fd)
        os.close(slave_fd)

    assert result["decision"] == "ULX3S_PROOF_EDGE_HIL_SUPPORTED"
    assert result["passed"] is True
    assert result["physical_board_executed"] is True
    assert result["required_repetitions"] == 10
    assert result["attempted_repetitions"] == 10
    assert result["successful_repetitions"] == 10
    assert all(row["oracle_match"] for row in result["repetitions"])
    assert len(result["evidence_inventory"]) == 62
