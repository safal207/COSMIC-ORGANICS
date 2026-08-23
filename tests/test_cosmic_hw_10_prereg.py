from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.cosmic_hw_10_oracle import PAD_LEAF, TREE_LEAVES, TREE_LEVELS, derive_oracle, parent_hash

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "cosmic_hw_10_manifest.json"
CANDIDATE = ROOT / "rtl" / "cosmic_hw_10_merkle.v"


def test_manifest_contract() -> None:
    m = json.loads(MANIFEST.read_text())
    assert m["experiment_id"] == "COSMIC-HW-10/v0.1"
    assert m["parent_hw09_source_head"] == "2cbc6442ff81f49ff6e247ffc5552ca2efa54c3d"
    assert m["selected_baseline"] == "SHA256x2"
    assert m["tree"]["leaf_capacity"] == 16
    assert m["tree"]["levels"] == 4
    assert m["tree"]["parent_message_bytes"] == 65
    assert m["tree"]["parent_sha_blocks"] == 2
    assert m["architecture"]["dedicated_merkle_sha_engines"] == 1
    assert m["architecture"]["tree_buffers"] == 1
    assert m["synthetic_combined_score"] is False


def test_candidate_rtl_absent_before_frozen_oracle() -> None:
    assert not CANDIDATE.exists()


def test_hash_domains_and_shape() -> None:
    assert TREE_LEAVES == 16
    assert TREE_LEVELS == 4
    assert PAD_LEAF == hashlib.sha256(b"COSMIC-HW-10/PAD").digest()
    left = bytes(range(32))
    right = bytes(reversed(range(32)))
    assert parent_hash(left, right) == hashlib.sha256(b"\x01" + left + right).digest()
    assert parent_hash(left, right) != parent_hash(right, left)


def test_derived_oracle_internal_consistency() -> None:
    o = derive_oracle()
    assert o["protocol"] == "COSMIC-HW-10/v0.1"
    assert o["source_sequences"] == 320
    assert o["real_leaves"] == 4240
    assert o["proof_fragments"] == 4 * 4240
    assert o["verified_real_leaf_proofs"] == 4240
    assert o["parent_hashes"] == 15 * o["tree_count"]
    assert o["parent_compression_blocks"] == 2 * o["parent_hashes"]
    assert o["parent_sha_rounds"] == 64 * o["parent_compression_blocks"]
    assert sum(o["digest_counts_by_sequence"]) == 4240
    assert len(o["digest_counts_by_sequence"]) == 320
    assert len(o["tree_counts_by_sequence"]) == 320
    assert len(o["oracle_fingerprint"]) == 64
