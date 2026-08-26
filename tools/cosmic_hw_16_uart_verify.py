from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

FRAME_BYTES = 60
PAYLOAD_BYTES = 56
MAGIC = b"CO16"
PROTOCOL_VERSION = 1
PROFILE_ID = 2


def _receipt_bytes(
    logical_tick: int,
    site_id: int,
    phase_before: int,
    phase_after: int,
    stimulus_s100: int,
    ordinal: int,
) -> bytes:
    value = (
        ((logical_tick & 0xFFFF) << 24)
        | ((site_id & 0x3F) << 18)
        | ((phase_before & 0x3) << 16)
        | ((phase_after & 0x3) << 14)
        | ((stimulus_s100 & 0xFF) << 6)
        | (ordinal & 0x3F)
    )
    return value.to_bytes(5, "big")


def expected_receipts() -> list[bytes]:
    rows: list[bytes] = []
    for logical_tick, before, after in ((1, 0, 1), (2, 1, 2)):
        for site_id in range(64):
            rows.append(
                _receipt_bytes(
                    logical_tick,
                    site_id,
                    before,
                    after,
                    100,
                    site_id,
                )
            )
    return rows


def expected_digests() -> list[bytes]:
    receipts = expected_receipts()
    digests: list[bytes] = []
    sequence = 0
    for offset in range(0, 120, 10):
        message = (
            (0x434F).to_bytes(2, "big")
            + sequence.to_bytes(2, "big")
            + b"".join(receipts[offset : offset + 10])
        )
        if len(message) != 54:
            raise AssertionError(len(message))
        digests.append(hashlib.sha256(message).digest())
        sequence += 1

    partial = b"".join(receipts[120:]) + bytes(10)
    message = (
        (0x4348).to_bytes(2, "big")
        + sequence.to_bytes(2, "big")
        + partial
    )
    if len(message) != 54:
        raise AssertionError(len(message))
    digests.append(hashlib.sha256(message).digest())
    return digests


def expected_phase_checksum() -> int:
    checksum = 0xC016A5A5
    for site_id in range(64):
        checksum = ((checksum << 5) | (checksum >> 27)) & 0xFFFFFFFF
        checksum ^= (site_id << 2) | 2
    return checksum


def build_expected_frame() -> bytes:
    digests = expected_digests()
    payload = bytearray()
    payload.extend(MAGIC)
    payload.extend((PROTOCOL_VERSION, PROFILE_ID))
    payload.extend(struct.pack("<H", 0))
    payload.extend(struct.pack("<H", 2))
    payload.extend(struct.pack("<I", 128))
    payload.extend(struct.pack("<H", len(digests)))
    payload.extend(struct.pack("<I", expected_phase_checksum()))
    payload.extend(struct.pack("<H", len(digests) - 1))
    payload.extend(digests[-1])
    payload.extend(struct.pack("<H", 0))
    if len(payload) != PAYLOAD_BYTES:
        raise AssertionError(len(payload))
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    return bytes(payload) + struct.pack("<I", crc)


def parse_frame(frame: bytes) -> dict:
    if len(frame) != FRAME_BYTES:
        raise ValueError(f"expected {FRAME_BYTES} bytes, got {len(frame)}")
    if frame[:4] != MAGIC:
        raise ValueError(f"bad magic: {frame[:4]!r}")

    payload = frame[:PAYLOAD_BYTES]
    observed_crc = struct.unpack_from("<I", frame, PAYLOAD_BYTES)[0]
    computed_crc = zlib.crc32(payload) & 0xFFFFFFFF
    if observed_crc != computed_crc:
        raise ValueError(
            f"CRC mismatch: observed={observed_crc:08x} computed={computed_crc:08x}"
        )

    return {
        "magic": frame[:4].decode("ascii"),
        "protocol_version": frame[4],
        "profile_id": frame[5],
        "run_ordinal": struct.unpack_from("<H", frame, 6)[0],
        "accepted_tick_count": struct.unpack_from("<H", frame, 8)[0],
        "receipt_count": struct.unpack_from("<I", frame, 10)[0],
        "digest_count": struct.unpack_from("<H", frame, 14)[0],
        "final_phase_checksum": struct.unpack_from("<I", frame, 16)[0],
        "last_digest_sequence": struct.unpack_from("<H", frame, 20)[0],
        "last_digest": frame[22:54].hex(),
        "error_flags": struct.unpack_from("<H", frame, 54)[0],
        "crc32": observed_crc,
        "frame_hex": frame.hex(),
    }


def verify_frame(frame: bytes) -> dict:
    observed = parse_frame(frame)
    expected_frame = build_expected_frame()
    expected = parse_frame(expected_frame)
    field_match = {
        key: observed[key] == expected[key]
        for key in (
            "magic",
            "protocol_version",
            "profile_id",
            "run_ordinal",
            "accepted_tick_count",
            "receipt_count",
            "digest_count",
            "final_phase_checksum",
            "last_digest_sequence",
            "last_digest",
            "error_flags",
        )
    }
    passed = all(field_match.values()) and frame == expected_frame
    return {
        "passed": passed,
        "field_match": field_match,
        "observed": observed,
        "expected": expected,
        "expected_commitment_digests": [row.hex() for row in expected_digests()],
        "expected_frame_sha256": hashlib.sha256(expected_frame).hexdigest(),
    }


def _load_frame(args: argparse.Namespace) -> bytes:
    if args.frame_hex:
        return bytes.fromhex("".join(args.frame_hex.split()))
    if args.frame_file:
        data = Path(args.frame_file).read_bytes()
        if args.input_format == "hex":
            return bytes.fromhex(data.decode("ascii").strip())
        return data
    return build_expected_frame()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a COSMIC-HW-16 CO16 UART evidence frame."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--frame-hex")
    source.add_argument("--frame-file")
    parser.add_argument("--input-format", choices=("binary", "hex"), default="binary")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-json")
    args = parser.parse_args()

    try:
        result = verify_frame(_load_frame(args))
    except (ValueError, OSError) as error:
        result = {"passed": False, "error": str(error)}

    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.write_json:
        Path(args.write_json).write_text(rendered + "\n", encoding="utf-8")
    if args.json or not args.write_json:
        print(rendered)
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    sys.exit(main())
