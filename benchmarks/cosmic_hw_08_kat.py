from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass

KAT_SEED = 202608230801
FULL_DOMAIN = 0x434F
PARTIAL_DOMAIN_BASE = 0x4340
RECEIPTS_PER_BLOCK = 10
EXPECTED_KAT_FINGERPRINT = "3919530f4fb110bb453429fb50d8f6c6f664cf9506f5391a4b3a1e9fac5d5bbd"

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@dataclass(frozen=True)
class CanonicalKat:
    sequence: int
    receipts_hex: tuple[str, ...]
    message_hex: str
    digest_hex: str


def _receipt_bytes(receipt: int) -> bytes:
    if not 0 <= receipt < (1 << 40):
        raise ValueError("receipt must fit 40 bits")
    return receipt.to_bytes(5, "big")


def canonical_message(sequence: int, receipts: list[int] | tuple[int, ...]) -> bytes:
    if not 0 <= sequence < (1 << 16):
        raise ValueError("sequence must fit 16 bits")
    count = len(receipts)
    if not 1 <= count <= RECEIPTS_PER_BLOCK:
        raise ValueError("receipt count must be 1..10")

    domain = FULL_DOMAIN if count == RECEIPTS_PER_BLOCK else (PARTIAL_DOMAIN_BASE | count)
    padded = list(receipts) + [0] * (RECEIPTS_PER_BLOCK - count)
    message = domain.to_bytes(2, "big") + sequence.to_bytes(2, "big")
    message += b"".join(_receipt_bytes(r) for r in padded)
    assert len(message) == 54
    return message


def sha256_one_block_padding(message: bytes) -> bytes:
    if len(message) > 55:
        raise ValueError("HW-08/v0.1 only preregisters one-block SHA-256 messages")
    bit_length = len(message) * 8
    out = message + b"\x80"
    out += b"\x00" * (56 - len(out))
    out += bit_length.to_bytes(8, "big")
    assert len(out) == 64
    return out


def generate_full_batch_kats() -> list[CanonicalKat]:
    rng = random.Random(KAT_SEED)
    vectors: list[CanonicalKat] = []
    for sequence in range(128):
        receipts = [rng.getrandbits(40) for _ in range(RECEIPTS_PER_BLOCK)]
        message = canonical_message(sequence, receipts)
        vectors.append(
            CanonicalKat(
                sequence=sequence,
                receipts_hex=tuple(f"{r:010x}" for r in receipts),
                message_hex=message.hex(),
                digest_hex=hashlib.sha256(message).hexdigest(),
            )
        )
    return vectors


def kat_fingerprint() -> str:
    payload = {
        "seed": KAT_SEED,
        "vectors": [
            {
                "sequence": v.sequence,
                "receipts_hex": list(v.receipts_hex),
                "message_hex": v.message_hex,
                "digest_hex": v.digest_hex,
            }
            for v in generate_full_batch_kats()
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def prereg_summary() -> dict[str, object]:
    vectors = generate_full_batch_kats()
    partial = {}
    for count in (1, 5, 9):
        receipts = list(range(1, count + 1))
        msg = canonical_message(0x1200 + count, receipts)
        partial[str(count)] = {
            "message_hex": msg.hex(),
            "digest_hex": hashlib.sha256(msg).hexdigest(),
            "padded_block_hex": sha256_one_block_padding(msg).hex(),
        }
    return {
        "kat_seed": KAT_SEED,
        "kat_count": len(vectors),
        "kat_fingerprint": kat_fingerprint(),
        "standard_kats": {"empty": EMPTY_SHA256, "abc": ABC_SHA256},
        "partial_kats": partial,
    }
