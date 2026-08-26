from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_17_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def test_identity_parent_and_question_are_frozen() -> None:
    m = load_manifest()
    assert m["benchmark_id"] == "COSMIC-HW-17-PREREG"
    assert m["protocol"] == "COSMIC-HW-17/v0.1"
    assert m["issue_number"] == 118
    assert m["parent"]["experiment"] == "COSMIC-HW-16/v0.1"
    assert m["parent"]["source_head"] == "1bb067bb7b325405eca703a16536eea79495410e"
    assert m["parent"]["frozen_result_branch"] == "research/cosmic-hw-16-frozen-result"
    assert m["parent"]["decision"] == "ULX3S_ROUTE_OR_TIMING_NOT_SUPPORTED"
    assert m["parent"]["artifact_id"] == 9592648059
    assert m["parent"]["artifact_digest"] == (
        "sha256:0ede795c94b30f7cf93745ebbd63e8a906c9eb0f4b0cb7703bf1ebe33a55e9bd"
    )
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", m["parent"]["source_head"], "HEAD"],
        cwd=ROOT,
        check=True,
    )


def test_only_timeout_intervention_is_admitted() -> None:
    m = load_manifest()
    i = m["intervention"]
    assert i == {
        "automatic_retry_allowed": False,
        "candidate_id": "T2400_CANDIDATE",
        "candidate_timeout_seconds": 2400,
        "constraint_edits_allowed": False,
        "control_id": "T1200_FROZEN_CONTROL",
        "control_timeout_seconds": 1200,
        "only_admitted_change": "per_seed_nextpnr_timeout_seconds",
        "replacement_seed_allowed": False,
        "rtl_edits_allowed": False,
        "stop_early_after_three_passes_allowed": False,
        "tool_option_edits_allowed": False,
    }
    assert m["seeds"] == [1601, 1602, 1603, 1604, 1605]
    assert m["parent"]["fully_qualified_seeds"] == [1603, 1605]
    assert m["parent"]["timed_out_seeds"] == [1601, 1602, 1604]


def test_board_toolchain_and_handoff_gate_are_frozen() -> None:
    m = load_manifest()
    b = m["board"]
    assert b["name"] == "ULX3S-85F"
    assert b["fpga"] == "LFE5U-85F-6BG381C"
    assert b["density_flag"] == "--85k"
    assert b["package"] == "CABGA381"
    assert b["speed_grade"] == 6
    assert b["input_clock_mhz"] == 25.0
    assert b["processor_clock_mhz"] == 10.0
    assert b["larger_device_fallback_allowed"] is False

    t = m["toolchain"]
    assert t["runner"] == "ubuntu-24.04"
    assert t["yosys"] == "0.33-5build2"
    assert t["iverilog"] == "12.0-2build2"
    assert t["nextpnr_ecp5"] == "0.6-3build5"
    assert t["project_trellis"] == "1.4-2build4"
    assert t["synthesis"] == "synth_ecp5 -nodsp"

    h = m["handoff_gate"]
    assert h["minimum_fully_qualified_seeds"] == 3
    assert h["maximum_comb_fraction"] == 0.85
    assert h["maximum_ff_fraction"] == 0.85
    assert h["required_mult18x18d"] == 0
    assert h["canonical_bitstream_rule"] == "lowest-numbered fully qualified seed"
    assert h["synthetic_combined_score_allowed"] is False


def test_parent_evidence_and_oracle_are_exact() -> None:
    m = load_manifest()
    p = m["parent"]
    assert p["synthesis"] == {
        "trellis_comb": 56262,
        "trellis_ff": 9286,
        "mult18x18d": 0,
        "ehxplll": 1,
    }
    assert p["minimum_fully_qualified_seeds"] == 3
    assert p["per_seed_timeout_seconds"] == 1200
    assert p["completed_seed_evidence"]["1603"]["bitstream_sha256"] == (
        "853f921585714abdbc3b236702224c5eb13767a208370f72c449f092db77267a"
    )
    assert p["completed_seed_evidence"]["1605"]["bitstream_sha256"] == (
        "d9d9ad088b73036487cdb016b891b2259a75ce5bb30f80a7e46ae95d18983c18"
    )

    o = m["frozen_oracle"]
    assert o == {
        "accepted_tick_count": 2,
        "digest_count": 13,
        "error_flags": 0,
        "final_phase_checksum": 1072257626,
        "frame_sha256": "16d448b3c5af0a09edc1817c6cf980f12d4806f0b6cfe969b2b524538e7e799b",
        "last_digest": "c31bff9259318b3309bdb0fdd5282ce58366d6d8d1b9c636080eb6482a230ab2",
        "last_digest_sequence": 12,
        "receipt_count": 128,
    }


def test_inherited_source_blobs_are_unchanged() -> None:
    m = load_manifest()
    for relative, expected in m["inherited_source_blobs"].items():
        path = ROOT / relative
        assert path.is_file(), relative
        assert git_blob_sha(path) == expected, relative


def test_matrix_and_same_seed_qualification_are_fail_closed() -> None:
    m = load_manifest()
    e = m["execution_shape"]
    assert e["seed_matrix"] == [1601, 1602, 1603, 1604, 1605]
    assert e["one_attempt_per_seed"] is True
    assert e["parallel_seed_execution_allowed"] is True
    assert e["common_netlist_fingerprint_required"] is True
    assert e["exactly_five_unique_seed_records_required"] is True
    assert e["canonical_push_run_only_publishes_evidence"] is True

    q = m["per_seed_qualification"]
    assert q["same_seed_must_route_pack_and_meet_both_clocks"] is True
    assert all(q.values())


def test_decisions_stop_rule_and_candidate_absence_are_frozen() -> None:
    m = load_manifest()
    assert m["decision_classes"] == [
        "CONTROL_FAILURE",
        "EXTENDED_BUDGET_SEMANTIC_FAILURE",
        "NO_EXTENDED_BUDGET_BOARD_HANDOFF",
        "ULX3S_EXTENDED_BUDGET_BITSTREAM_READY",
    ]
    assert m["diagnosis_classes"] == [
        "TIMEOUT_CENSORING_OBSERVED",
        "ROUTE_RUNTIME_VARIABILITY_OBSERVED",
        "PARENT_COMPLETION_PATTERN_REPRODUCED",
    ]
    assert not any(m["stop_rule"].values())
    for relative in m["candidate_paths"]:
        assert not (ROOT / relative).exists(), relative
