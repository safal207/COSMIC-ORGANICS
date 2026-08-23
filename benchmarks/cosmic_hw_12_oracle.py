from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from benchmarks.cosmic_hw_07_candidate import build_oracle
from benchmarks.cosmic_hw_08_candidate import expected_commitments
from benchmarks.cosmic_hw_10_candidate import expected_merkle

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "benchmarks" / "cosmic_hw_12_manifest.json"
DOMAIN = bytes.fromhex("434f3132")
KEY_SEED = b"COSMIC-HW-12/TEST-KEY"
TEST_KEY = hashlib.sha256(KEY_SEED).digest()

RFC_STYLE_KATS = [
    {
        "name": "rfc4231_case1",
        "key": bytes([0x0B]) * 20,
        "message": b"Hi There",
        "expected_hex": "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7",
    },
    {
        "name": "rfc4231_case2",
        "key": b"Jefe",
        "message": b"what do ya want for nothing?",
        "expected_hex": "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843",
    },
]


def canonical_record(source_sequence: int, tree_ordinal: int, real_leaf_count: int, root_digest: bytes) -> bytes:
    if not (0 <= source_sequence <= 0xFFFF):
        raise ValueError("source_sequence out of range")
    if not (0 <= tree_ordinal <= 0xFFFF):
        raise ValueError("tree_ordinal out of range")
    if not (1 <= real_leaf_count <= 16):
        raise ValueError("real_leaf_count out of range")
    if len(root_digest) != 32:
        raise ValueError("root_digest must be 32 bytes")
    record = (
        DOMAIN
        + source_sequence.to_bytes(2, "big")
        + tree_ordinal.to_bytes(2, "big")
        + real_leaf_count.to_bytes(1, "big")
        + root_digest
    )
    if len(record) != 41:
        raise AssertionError(f"canonical HW-12 record length mismatch: {len(record)}")
    return record


def frozen_pairs() -> list[dict[str, object]]:
    execution = build_oracle()
    commitments = expected_commitments(execution)
    merkle = expected_merkle(execution, commitments)
    roots = merkle["roots"]
    if len(roots) != 444:
        raise RuntimeError(f"frozen root count mismatch: {len(roots)}")

    pairs: list[dict[str, object]] = []
    for index, row in enumerate(roots):
        root_bytes = int(row["root"]).to_bytes(32, "big")
        record = canonical_record(
            int(row["source_sequence"]),
            int(row["tree_ordinal"]),
            int(row["real_leaf_count"]),
            root_bytes,
        )
        tag = hmac.new(TEST_KEY, record, hashlib.sha256).digest()
        pairs.append(
            {
                "index": index,
                "source_sequence": int(row["source_sequence"]),
                "tree_ordinal": int(row["tree_ordinal"]),
                "real_leaf_count": int(row["real_leaf_count"]),
                "root_hex": root_bytes.hex(),
                "record_hex": record.hex(),
                "tag_hex": tag.hex(),
            }
        )
    return pairs


def fingerprint(pairs: list[dict[str, object]]) -> str:
    payload = bytearray()
    for row in pairs:
        payload.extend(bytes.fromhex(str(row["record_hex"])))
        payload.extend(bytes.fromhex(str(row["tag_hex"])))
    return hashlib.sha256(bytes(payload)).hexdigest()


def verify_rfc_style_kats() -> None:
    for vector in RFC_STYLE_KATS:
        got = hmac.new(vector["key"], vector["message"], hashlib.sha256).hexdigest()
        if got != vector["expected_hex"]:
            raise RuntimeError(f"HMAC KAT failed {vector['name']}: got={got}")


def summary() -> dict[str, object]:
    verify_rfc_style_kats()
    pairs = frozen_pairs()
    return {
        "test_key_hex": TEST_KEY.hex(),
        "record_count": len(pairs),
        "record_bytes": len(bytes.fromhex(str(pairs[0]["record_hex"]))),
        "tag_bytes": len(bytes.fromhex(str(pairs[0]["tag_hex"]))),
        "fingerprint": fingerprint(pairs),
        "rfc_style_kats": len(RFC_STYLE_KATS),
        "first_pair": pairs[0],
        "last_pair": pairs[-1],
    }


def main() -> None:
    result = summary()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
