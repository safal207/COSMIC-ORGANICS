from __future__ import annotations

import hashlib
import json
from pathlib import Path

from benchmarks.cosmic_hw_08_kat import (
    ABC_SHA256,
    EMPTY_SHA256,
    EXPECTED_KAT_FINGERPRINT,
    FULL_DOMAIN,
    KAT_SEED,
    canonical_message,
    generate_full_batch_kats,
    kat_fingerprint,
    sha256_one_block_padding,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "cosmic_hw_08_manifest.json"
CANDIDATE_RTL = ROOT / "rtl" / "cosmic_hw_08_sha256.v"


def test_manifest_is_frozen_and_candidate_absent() -> None:
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["experiment_id"] == "COSMIC-HW-08/v0.1"
    assert manifest["parent_hw07_green_head"] == "1e71648e1a2f375d7eeb3147a301a81dc8bc2399"
    assert manifest["parent_hw07b_head"] == "9ad5b01b9960a49f4800dbffcdf96b4dac50bd6e"
    assert manifest["parent_hw07b_decision"] == "NO_VALID_MICROARCHITECTURE_IMPROVEMENT"
    assert manifest["selected_receipt_baseline"] == "CONTROL_F4_FLAT"
    assert manifest["known_answer_tests"]["canonical_receipt_batches"] == 128
    assert manifest["known_answer_tests"]["kat_seed"] == KAT_SEED
    assert manifest["sha256_core"]["engines"] == 1
    assert manifest["sha256_core"]["rounds_per_cycle"] == 1
    assert manifest["assembler"]["complete_waiting_blocks"] == 1
    assert manifest["metrics"]["synthetic_combined_score_allowed"] is False
    assert manifest["deferred"]["merkle_tree"] is True
    assert not CANDIDATE_RTL.exists()


def test_standard_sha256_reference_vectors() -> None:
    assert hashlib.sha256(b"").hexdigest() == EMPTY_SHA256
    assert hashlib.sha256(b"abc").hexdigest() == ABC_SHA256


def test_128_frozen_full_batch_kats() -> None:
    vectors = generate_full_batch_kats()
    assert len(vectors) == 128
    assert kat_fingerprint() == EXPECTED_KAT_FINGERPRINT
    assert len({v.message_hex for v in vectors}) == 128
    assert len({v.digest_hex for v in vectors}) == 128
    for sequence, vector in enumerate(vectors):
        assert vector.sequence == sequence
        message = bytes.fromhex(vector.message_hex)
        assert len(message) == 54
        assert message[:2] == FULL_DOMAIN.to_bytes(2, "big")
        assert int.from_bytes(message[2:4], "big") == sequence
        assert hashlib.sha256(message).hexdigest() == vector.digest_hex
        block = sha256_one_block_padding(message)
        assert len(block) == 64
        assert int.from_bytes(block[-8:], "big") == 432


def test_partial_domain_and_zero_fill_are_explicit() -> None:
    for count in range(1, 10):
        receipts = list(range(1, count + 1))
        sequence = 0x4000 + count
        message = canonical_message(sequence, receipts)
        assert len(message) == 54
        assert int.from_bytes(message[:2], "big") == (0x4340 | count)
        assert int.from_bytes(message[2:4], "big") == sequence
        payload = message[4:]
        for index, receipt in enumerate(receipts):
            assert int.from_bytes(payload[index * 5 : index * 5 + 5], "big") == receipt
        for index in range(count, 10):
            assert payload[index * 5 : index * 5 + 5] == b"\x00" * 5
        assert int.from_bytes(sha256_one_block_padding(message)[-8:], "big") == 432


def test_full_domain_is_not_used_for_partial_batches() -> None:
    full = canonical_message(7, list(range(10)))
    partial = canonical_message(7, list(range(9)))
    assert int.from_bytes(full[:2], "big") == FULL_DOMAIN
    assert int.from_bytes(partial[:2], "big") == 0x4349
    assert full != partial


def test_one_block_boundary_is_exact() -> None:
    message = canonical_message(0, [0] * 10)
    padded = sha256_one_block_padding(message)
    assert len(message) == 54
    assert padded[54] == 0x80
    assert padded[55] == 0x00
    assert padded[56:] == (432).to_bytes(8, "big")
