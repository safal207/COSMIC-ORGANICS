from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import tools.cosmic_hw_22_causal_transition as hw22
from tools.cosmic_hw_22_causal_transition import (
    CONTROL_POLICY,
    EAGER_POLICY,
    EXPECTED_PARENT_HEAD,
    EXPECTED_PARENT_TREE,
    EXPECTED_VECTOR_BLOB,
    EXPECTED_VECTOR_FILE_SHA256,
    EXPECTED_VECTOR_FINGERPRINT,
    LAYERS,
    POLICIES,
    closed_form_cycles,
    load_manifest,
    load_oracle,
    make_testbench,
    model_timeline,
    require_expected_head,
    simulate_policy,
)


ROOT = Path(__file__).resolve().parents[1]
RTL_PATH = ROOT / "rtl" / "cosmic_hw_21_network_pyramid.v"

CONTROL_EXPECTED = {1: 862, 2: 482, 3: 362, 4: 307, 5: 287, 6: 262, 7: 257, 8: 257}
EAGER_EXPECTED = {1: 859, 2: 469, 3: 339, 4: 274, 5: 229, 6: 209, 7: 198, 8: 198}


def independent_reference(engines: int, eager: bool) -> dict[str, object]:
    reusable = [0] * engines
    previous_retire = 0
    block_ready = 12
    rows: list[tuple[int, int, int, int]] = []
    for sequence in range(12):
        accept = max(block_ready + 1, min(reusable))
        selected = min(index for index, value in enumerate(reusable) if value <= accept)
        retire = max(accept + 65, previous_retire + 1)
        rows.append((sequence, block_ready, accept, retire))
        reusable[selected] = retire
        previous_retire = retire
        if sequence != 11:
            block_ready = max(block_ready + 10, accept)
    last_receipt = rows[-1][1] + 8
    if eager:
        first_flush = last_receipt + 1
        partial_ready = max(first_flush, rows[-1][2] + 1)
    else:
        first_flush = rows[-1][3] + 2
        partial_ready = first_flush
    partial_accept = max(partial_ready + 1, min(reusable))
    partial_retire = max(partial_accept + 65, previous_retire + 1)
    return {
        "completion": partial_retire + 1,
        "full_accepts": [row[2] for row in rows],
        "last_receipt": last_receipt,
        "first_flush": first_flush,
        "partial_ready": partial_ready,
        "partial_accept": partial_accept,
    }


def test_manifest_freezes_exact_hw21_evidence() -> None:
    manifest = load_manifest()
    parent = manifest["parent"]
    assert parent["source_head"] == EXPECTED_PARENT_HEAD
    assert parent["source_tree"] == EXPECTED_PARENT_TREE
    assert parent["pull_request"] == 124
    assert parent["workflow_run_id"] == 33363461183
    assert parent["artifact_id"] == 9747638157
    assert parent["artifact_sha256"] == "b06eaa90d1539af80aefebe0e5ed7dd30effaecc7ca0a5543ae9b6d658fb8c8e"
    assert parent["physical_execution_state"] == "NOT_RUN"


def test_oracle_is_frozen_independent_and_complete() -> None:
    manifest = load_manifest()
    digests = load_oracle(manifest)
    vector_path = ROOT / "benchmarks" / "cosmic_hw_16_vectors.json"
    framed = b"".join(index.to_bytes(2, "big") + digest for index, digest in enumerate(digests))
    assert len(digests) == 13
    assert hw22.git_blob_sha(vector_path) == EXPECTED_VECTOR_BLOB
    assert hashlib.sha256(vector_path.read_bytes()).hexdigest() == EXPECTED_VECTOR_FILE_SHA256
    assert hashlib.sha256(framed).hexdigest() == EXPECTED_VECTOR_FINGERPRINT
    assert [digest.hex() for digest in digests] == json.loads(
        vector_path.read_text(encoding="utf-8")
    )["commitment_digests"]


def test_short_oracle_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    malformed = tmp_path / "short.json"
    malformed.write_text(
        json.dumps({"digest_count": 1, "commitment_digests": ["00" * 32]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(hw22, "VECTOR_PATH", malformed)
    with pytest.raises(RuntimeError, match="exactly 13"):
        load_oracle(load_manifest())


def test_independent_max_plus_reference_matches_preregistration() -> None:
    manifest = load_manifest()
    assert tuple(manifest["causal_experiment"]["engine_counts"]) == LAYERS
    assert tuple(manifest["causal_experiment"]["policies"]) == POLICIES
    for engines in LAYERS:
        control = independent_reference(engines, eager=False)
        eager = independent_reference(engines, eager=True)
        assert control["completion"] == CONTROL_EXPECTED[engines]
        assert eager["completion"] == EAGER_EXPECTED[engines]
        assert closed_form_cycles(engines, CONTROL_POLICY) == CONTROL_EXPECTED[engines]
        assert closed_form_cycles(engines, EAGER_POLICY) == EAGER_EXPECTED[engines]
        assert model_timeline(engines, CONTROL_POLICY)["completion_cycle"] == CONTROL_EXPECTED[engines]
        assert model_timeline(engines, EAGER_POLICY)["completion_cycle"] == EAGER_EXPECTED[engines]
        assert manifest["model"]["preregistered_compute_cycles"][CONTROL_POLICY][str(engines)] == CONTROL_EXPECTED[engines]
        assert manifest["model"]["preregistered_compute_cycles"][EAGER_POLICY][str(engines)] == EAGER_EXPECTED[engines]
    assert CONTROL_EXPECTED[2] == 482
    assert CONTROL_EXPECTED[4] == 307
    assert CONTROL_EXPECTED[8] == 257


def test_generated_testbench_checks_every_digest_and_holds_flush() -> None:
    digests = load_oracle(load_manifest())
    eager_text = make_testbench(7, EAGER_POLICY, digests)
    control_text = make_testbench(7, CONTROL_POLICY, digests)
    assert "localparam integer ENGINES = 7;" in eager_text
    assert "localparam integer EAGER_HELD_FLUSH = 1;" in eager_text
    assert "localparam integer EAGER_HELD_FLUSH = 0;" in control_text
    assert "digest_valid && digest_ready" in eager_text
    assert "digest_data !==" in eager_text
    assert "digest_sequence !== digest_count" in eager_text
    assert "producer_end_seen" in eager_text
    assert "accept_mask != 0 && dut.waiting_sequence == 12" in eager_text
    assert "quiet_guard_cycles == 16" in eager_text
    assert "aggregate_busy_cycles != 832" in eager_text
    for sequence, digest in enumerate(digests):
        assert f"16'd{sequence}:" in eager_text
        assert digest.hex() in eager_text.lower()


def test_synthesizable_rtl_contains_no_oracle_digest() -> None:
    rtl = RTL_PATH.read_text(encoding="utf-8").lower()
    for digest in load_oracle(load_manifest()):
        assert digest.hex() not in rtl


def test_candidate_paths_are_bounded_and_do_not_add_rtl() -> None:
    assert set(load_manifest()["candidate_paths"]) == {
        ".github/workflows/cosmic_hw_22_causal_transition_contract.yml",
        "benchmarks/cosmic_hw_22_causal_manifest.json",
        "docs/cosmic-hw-22-causal-transition.md",
        "tests/test_cosmic_hw_22_causal_transition.py",
        "tools/cosmic_hw_22_causal_transition.py",
    }
    assert not any(path.startswith("rtl/") for path in load_manifest()["candidate_paths"])


def test_exact_head_must_be_supplied_externally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COSMIC_HW22_EXPECTED_HEAD", raising=False)
    with pytest.raises(RuntimeError, match="requires COSMIC_HW22_EXPECTED_HEAD"):
        require_expected_head()
    monkeypatch.setenv("COSMIC_HW22_EXPECTED_HEAD", EXPECTED_PARENT_HEAD)
    assert require_expected_head() == EXPECTED_PARENT_HEAD


def test_e3_counterfactual_exercises_lost_pulse_hazard(tmp_path: Path) -> None:
    if shutil.which("iverilog") is None or shutil.which("vvp") is None:
        pytest.skip("cycle-accurate simulator unavailable; HW-22 CI installs Icarus 12.0")
    manifest = load_manifest()
    digests = load_oracle(manifest)
    log_dir = tmp_path / "runs"
    log_dir.mkdir()
    control = simulate_policy(tmp_path, log_dir, 3, CONTROL_POLICY, manifest, digests)
    eager = simulate_policy(tmp_path, log_dir, 3, EAGER_POLICY, manifest, digests)
    assert control["compute_cycles"] == 362
    assert eager["compute_cycles"] == 339
    assert control["matched_digest_count"] == eager["matched_digest_count"] == 13
    assert control["aggregate_sha_busy_cycles"] == eager["aggregate_sha_busy_cycles"] == 832
    assert eager["flush"]["producer_quiescent_at_first_sample"] is True
    assert eager["flush"]["waiting_valid_at_first_sample"] is True
    assert eager["flush"]["retired_digests_at_first_sample"] < 12
    assert eager["flush"]["build_count"] == 1
    assert eager["quiet_guard"] == {"cycles": 16, "violations": 0}


def test_direct_entrypoint_is_runnable() -> None:
    process = subprocess.run(
        [sys.executable, "tools/cosmic_hw_22_causal_transition.py", "--help"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.returncode == 0, process.stdout
    assert "causal state-time transition" in process.stdout
