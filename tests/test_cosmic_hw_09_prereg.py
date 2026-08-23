from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "cosmic_hw_09_manifest.json"
CANDIDATE_RTL = ROOT / "rtl" / "cosmic_hw_09_multi_sha.v"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_protocol_and_parent_are_frozen() -> None:
    m = load_manifest()
    assert m["experiment_id"] == "COSMIC-HW-09/v0.1"
    assert m["parent_hw08_head"] == "84e1bbc8cd7cb42fba8e7f4de736ebf48161307d"
    assert m["parent_hw08_decision"] == "SHA256_COMMITMENT_COST_MEASURED"
    assert m["systems"] == ["SHA256x1_CONTROL", "SHA256x2", "SHA256x4"]


def test_receipt_and_sha_semantics_are_unchanged() -> None:
    m = load_manifest()
    r = m["receipt_contract"]
    assert r["width_bits"] == 40
    assert r["receipts_per_full_commitment"] == 10
    assert r["full_domain_hex"] == "434f"
    assert r["canonical_message_bytes"] == 54
    assert r["sha_block_bytes"] == 64
    assert r["collector_fifo_depth"] == 4
    s = m["sha_engine"]
    assert s["architecture"] == "iterative_64_round"
    assert s["rounds_per_cycle"] == 1
    assert s["rounds_per_digest"] == 64
    assert s["vendor_ip_allowed"] is False
    assert s["unrolled_64_round_datapath_allowed"] is False


def test_workload_and_control_evidence_are_frozen() -> None:
    m = load_manifest()
    w = m["workload"]
    assert w["total_sequences"] == 320
    assert w["accepted_logical_ticks"] == 3840
    assert w["real_receipts"] == 41144
    assert w["sha_blocks"] == 4240
    assert w["full_blocks"] == 3951
    assert w["partial_blocks"] == 289
    assert w["stress_fingerprint"] == "sha256:be033839531356f0695b6c270b8d22a2abb8f388dd1ecb9c4b93644c9b291110"

    c = m["frozen_x1_control"]
    assert c["physical_cycles"] == 280885
    assert c["sha_busy_cycles"] == 271360
    assert c["assembler_stalls"] == 191599
    assert c["digest_sink_stalls"] == 1001
    assert c["backpressure_stalls"] == {
        "0.01": 0,
        "0.05": 542,
        "0.20": 22914,
        "1.00": 26966,
        "stress": 57563,
    }
    assert c["synthesis"] == {
        "lut": 17713,
        "ff": 7872,
        "core_cells_excluding_io": 31226,
        "logic_depth_proxy": 266,
        "bram": 0,
        "lutram": 0,
    }


def test_throughput_gate_is_per_group_not_weighted() -> None:
    m = load_manifest()
    g = m["throughput_gates"]
    assert g["low_activity"] == {"0.01_max_stalls": 0, "0.05_max_stalls": 542}
    assert g["minimum_reduction_fraction_each_group"] == 0.5
    assert g["primary_groups"] == {"0.20": 22914, "1.00": 26966, "stress": 57563}
    assert g["average_or_weighted_rescue_allowed"] is False
    assert m["selection_rule"]["synthetic_combined_score_allowed"] is False


def test_multi_engine_dispatch_and_retirement_are_frozen() -> None:
    m = load_manifest()["multi_engine_dispatch"]
    assert m["engines"] == [1, 2, 4]
    assert m["currently_filling_messages"] == 1
    assert m["complete_waiting_blocks"] == 1
    assert m["dispatch_rule"] == "lowest_index_ready_engine"
    assert m["digest_retirement"] == "strictly_increasing_commitment_sequence"
    assert m["digest_selection_rule"] == "lowest_sequence_completed_digest_first"
    assert m["infinite_queue_allowed"] is False
    assert m["drop_allowed"] is False


def test_candidate_rtl_absent_before_prereg_green() -> None:
    assert not CANDIDATE_RTL.exists(), "candidate HW-09 RTL must not exist on prereg branch"


def test_merkle_and_other_claims_remain_deferred() -> None:
    d = load_manifest()["deferred"]
    assert all(d.values())
