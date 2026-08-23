from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.cosmic_hw_12_oracle import (
    DOMAIN,
    TEST_KEY,
    canonical_record,
    fingerprint,
    frozen_pairs,
    summary,
    verify_rfc_style_kats,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "cosmic_hw_12_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def test_frozen_parent_and_selected_control() -> None:
    m = load_manifest()
    assert m["experiment_id"] == "COSMIC-HW-12/v0.1"
    assert m["parent_hw11_source_head"] == "1ed75676e59a7a745ace852c8b24982dfb41a614"
    assert m["selected_control"] == "B1_M2"
    c = m["control"]
    assert c["tree_buffers"] == 1
    assert c["merkle_sha_engines"] == 2
    assert c["physical_cycles"] == 624253
    assert c["backpressure_stalls"] == {"0.01": 0, "0.05": 542, "0.20": 11184, "1.00": 13456, "stress": 56985}
    assert c["lut"] == 48437
    assert c["ff"] == 24287
    assert c["core_cells_excluding_io"] == 75967
    assert c["logic_depth_proxy"] == 266


def test_key_and_canonical_record_boundary() -> None:
    m = load_manifest()
    assert TEST_KEY.hex() == m["test_key"]["hex"]
    assert TEST_KEY == hashlib.sha256(b"COSMIC-HW-12/TEST-KEY").digest()
    assert DOMAIN == b"CO12"
    root = bytes(range(32))
    record = canonical_record(0x1234, 0x5678, 16, root)
    assert len(record) == 41
    assert record[:4] == b"CO12"
    assert record[4:6] == bytes.fromhex("1234")
    assert record[6:8] == bytes.fromhex("5678")
    assert record[8] == 16
    assert record[9:] == root


def test_standard_hmac_kats() -> None:
    verify_rfc_style_kats()


def test_frozen_root_hmac_oracle() -> None:
    m = load_manifest()
    pairs = frozen_pairs()
    assert len(pairs) == 444
    assert all(len(bytes.fromhex(str(x["record_hex"]))) == 41 for x in pairs)
    assert all(len(bytes.fromhex(str(x["tag_hex"]))) == 32 for x in pairs)
    got = fingerprint(pairs)
    frozen = m["frozen_oracle"]["fingerprint"]
    if frozen is not None:
        assert got == frozen


def test_frozen_hmac_work_accounting() -> None:
    h = load_manifest()["hmac"]
    assert h["compression_blocks_per_root"] == 4
    assert h["compression_rounds_per_root"] == 256
    assert h["frozen_roots"] == 444
    assert h["total_compression_blocks"] == 1776
    assert h["total_compression_rounds"] == 113664
    assert h["engines"] == 1
    assert h["pending_root_slots"] == 1
    assert h["completed_tag_slots"] == 1


def test_candidate_files_absent_on_prereg_head() -> None:
    m = load_manifest()
    assert not (ROOT / m["candidate_rtl_path"]).exists()
    assert not (ROOT / m["candidate_benchmark_path"]).exists()


def test_summary_matches_manifest_when_fingerprint_frozen() -> None:
    m = load_manifest()
    s = summary()
    assert s["test_key_hex"] == m["test_key"]["hex"]
    assert s["record_count"] == 444
    assert s["record_bytes"] == 41
    if m["frozen_oracle"]["fingerprint"] is not None:
        assert s["fingerprint"] == m["frozen_oracle"]["fingerprint"]
