from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from benchmarks.cosmic_board_01_oracle import build_oracle

SYNC = b"CO"
FRAME_START = 0x01
FRAME_DIGEST = 0x20
FRAME_END = 0x7F


class TranscriptError(ValueError):
    """Raised when a BOARD-01 UART transcript is malformed or non-canonical."""


@dataclass(frozen=True)
class Frame:
    """One decoded, CRC-checked BOARD-01 UART frame."""

    frame_type: int
    record_sequence: int
    payload: bytes


def crc16_ccitt_false(data: bytes) -> int:
    """Return CRC-16/CCITT-FALSE for the exact bytes on the protocol body."""

    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def parse_frames(data: bytes) -> list[Frame]:
    """Parse the complete transcript and reject truncation, garbage, or CRC drift."""

    frames: list[Frame] = []
    offset = 0
    expected_record_sequence = 0
    while offset < len(data):
        if len(data) - offset < 8:
            raise TranscriptError(f"truncated frame header at offset {offset}")
        if data[offset : offset + 2] != SYNC:
            raise TranscriptError(f"sync mismatch at offset {offset}")
        frame_type = data[offset + 2]
        payload_length = data[offset + 3]
        record_sequence = int.from_bytes(data[offset + 4 : offset + 6], "big")
        frame_length = 8 + payload_length
        if offset + frame_length > len(data):
            raise TranscriptError(f"truncated frame payload at offset {offset}")
        payload = data[offset + 6 : offset + 6 + payload_length]
        supplied_crc = int.from_bytes(
            data[offset + 6 + payload_length : offset + 8 + payload_length], "big"
        )
        body = data[offset + 2 : offset + 6 + payload_length]
        computed_crc = crc16_ccitt_false(body)
        if supplied_crc != computed_crc:
            raise TranscriptError(
                f"CRC mismatch at record {record_sequence}: "
                f"got 0x{supplied_crc:04x}, expected 0x{computed_crc:04x}"
            )
        if record_sequence != expected_record_sequence:
            raise TranscriptError(
                f"record sequence mismatch: got {record_sequence}, "
                f"expected {expected_record_sequence}"
            )
        frames.append(Frame(frame_type, record_sequence, payload))
        expected_record_sequence += 1
        offset += frame_length
    if not frames:
        raise TranscriptError("empty transcript")
    return frames


def _decode_end(payload: bytes) -> dict[str, Any]:
    if len(payload) != 49:
        raise TranscriptError(f"END payload length is {len(payload)}, expected 49")
    return {
        "status": payload[0],
        "accepted_ticks": int.from_bytes(payload[1:3], "big"),
        "receipt_count": int.from_bytes(payload[3:7], "big"),
        "digest_count": int.from_bytes(payload[7:9], "big"),
        "final_phase_hex": payload[9:25].hex(),
        "final_active_hex": payload[25:33].hex(),
        "final_changed_hex": payload[33:41].hex(),
        "final_dirty_hex": payload[41:49].hex(),
    }


def verify_transcript(data: bytes, *, require_oracle_equality: bool = True) -> dict[str, Any]:
    """Verify framing, semantic fields, digest ordering, and optional exact oracle equality."""

    frames = parse_frames(data)
    if frames[0].frame_type != FRAME_START:
        raise TranscriptError("first frame is not START")
    if frames[-1].frame_type != FRAME_END:
        raise TranscriptError("last frame is not END")
    if any(frame.frame_type != FRAME_DIGEST for frame in frames[1:-1]):
        raise TranscriptError("non-DIGEST frame found between START and END")

    start = frames[0].payload
    if len(start) != 12:
        raise TranscriptError(f"START payload length is {len(start)}, expected 12")
    if start != b"\x00\x01PES1\x00\x40L512":
        raise TranscriptError(f"START payload mismatch: {start.hex()}")

    digests: list[dict[str, Any]] = []
    for expected_sequence, frame in enumerate(frames[1:-1]):
        if len(frame.payload) != 34:
            raise TranscriptError(
                f"DIGEST payload length is {len(frame.payload)}, expected 34"
            )
        sequence = int.from_bytes(frame.payload[:2], "big")
        if sequence != expected_sequence:
            raise TranscriptError(
                f"commitment sequence mismatch: got {sequence}, "
                f"expected {expected_sequence}"
            )
        digests.append({"sequence": sequence, "digest_hex": frame.payload[2:].hex()})

    end = _decode_end(frames[-1].payload)
    if end["status"] != 0xA5:
        raise TranscriptError(f"terminal status is 0x{end['status']:02x}, expected 0xa5")
    if end["digest_count"] != len(digests):
        raise TranscriptError(
            f"END digest count {end['digest_count']} != parsed {len(digests)}"
        )

    transcript_hash = sha256(data).hexdigest()
    result: dict[str, Any] = {
        "verified": True,
        "frame_count": len(frames),
        "digest_count": len(digests),
        "transcript_bytes": len(data),
        "transcript_sha256": transcript_hash,
        "start": {
            "protocol_version": int.from_bytes(start[0:2], "big"),
            "profile_id": start[2:6].decode("ascii"),
            "expected_ticks": int.from_bytes(start[6:8], "big"),
            "generator_id": start[8:12].decode("ascii"),
        },
        "end": end,
        "first_digest_hex": digests[0]["digest_hex"] if digests else None,
        "last_digest_hex": digests[-1]["digest_hex"] if digests else None,
    }

    if require_oracle_equality:
        oracle = build_oracle()
        expected = oracle["summary"]
        expected_transcript = oracle["transcript"]
        if data != expected_transcript:
            raise TranscriptError(
                "transcript is structurally valid but differs from the frozen oracle: "
                f"got sha256={transcript_hash}, "
                f"expected sha256={expected['uart_transcript_sha256']}"
            )
        expected_end = {
            "status": 0xA5,
            "accepted_ticks": expected["ticks"],
            "receipt_count": expected["receipt_count"],
            "digest_count": expected["digest_count"],
            "final_phase_hex": expected["final_phase_hex"],
            "final_active_hex": expected["final_active_hex"],
            "final_changed_hex": expected["final_changed_hex"],
            "final_dirty_hex": expected["final_dirty_hex"],
        }
        if end != expected_end:
            raise TranscriptError(f"END record differs from oracle: {end} != {expected_end}")
        result["oracle_equal"] = True
    else:
        result["oracle_equal"] = None
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a COSMIC-BOARD-01 UART capture")
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--structure-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = verify_transcript(
            args.transcript.read_bytes(),
            require_oracle_equality=not args.structure_only,
        )
    except (OSError, TranscriptError) as error:
        if args.json:
            print(json.dumps({"verified": False, "error": str(error)}, indent=2))
        else:
            print(f"COSMIC_BOARD_01_VERIFY FAIL: {error}")
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "COSMIC_BOARD_01_VERIFY PASS "
            f"frames={result['frame_count']} digests={result['digest_count']} "
            f"sha256={result['transcript_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
