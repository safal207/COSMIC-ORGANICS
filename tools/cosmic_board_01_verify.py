from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.cosmic_hw_08_kat import canonical_message
from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.sparse_scheduler import DirtyNodeGrid2D


INITIAL_STIMULUS = int(
    "1f123bb5a55a0f0fc33ca5a56969f00fd15ea5e5c001d00dcafe5eed12345678"
    "89abcdef0123456776543210fedcba98a5a55a5ac3c33c3cf0f00f0f55aa55aa",
    16,
)
MASK_512 = (1 << 512) - 1
FRAME_MAGIC = b"CD"
FRAME_DIGEST = 0x01
FRAME_SUMMARY = 0x02
PROTOCOL_VERSION = 0x01
PROFILE_ID = 0x01
TERMINAL_OK = 0xA5
PHASE_CODE = {"A": 0, "M": 1, "C": 2}


class TranscriptError(ValueError):
    """Raised when a board transcript is malformed or disagrees with the oracle."""


def signed_byte(value: int) -> int:
    """Interpret one unsigned byte as the signed stimulus used by the RTL."""
    value &= 0xFF
    return value - 256 if value >= 128 else value


def lfsr_step(value: int) -> int:
    """Apply the exact frozen 512-bit board stimulus shift/tap rule."""
    feedback = (
        ((value >> 511) & 1)
        ^ ((value >> 509) & 1)
        ^ ((value >> 503) & 1)
        ^ ((value >> 500) & 1)
    )
    return ((value << 1) & MASK_512) | feedback


def mask_from_sites(sites: set[int] | list[int]) -> int:
    """Pack site indices into the 64-bit mask convention used by the RTL."""
    result = 0
    for site in sites:
        result |= 1 << site
    return result


def state_bits(state: str) -> int:
    """Pack the A/M/C state string into the 128-bit little-site-order bus."""
    result = 0
    for site, phase in enumerate(state):
        result |= PHASE_CODE[phase] << (2 * site)
    return result


def pack_receipt(
    logical_tick: int,
    site: int,
    phase_before: str,
    phase_after: str,
    stimulus_s100: int,
    ordinal: int,
) -> int:
    """Pack one receipt using the frozen 40-bit COSMIC-HW-07 contract."""
    return (
        ((logical_tick & 0xFFFF) << 24)
        | ((site & 0x3F) << 18)
        | ((PHASE_CODE[phase_before] & 0x3) << 16)
        | ((PHASE_CODE[phase_after] & 0x3) << 14)
        | ((stimulus_s100 & 0xFF) << 6)
        | (ordinal & 0x3F)
    )


def build_expected() -> dict[str, Any]:
    """Independently reproduce the frozen 64-tick board workload and evidence."""
    config = Grid2DConfig(width=8, height=8, memory_decay=0.0)
    dense = Grid2D("A" * 64, config=config)
    sparse = DirtyNodeGrid2D("A" * 64, config=config)
    previous_stimulus = [0] * 64
    stimulus_state = INITIAL_STIMULUS
    receipts: list[int] = []

    final_phase = 0
    final_active = 0
    final_changed = 0
    final_dirty = 0

    for logical_tick in range(1, 65):
        stimulus_s100 = tuple(
            signed_byte(stimulus_state >> (8 * site)) for site in range(64)
        )
        scheduled = set(sparse._dirty_next)
        scheduled.update(
            site
            for site, (previous, current) in enumerate(
                zip(previous_stimulus, stimulus_s100)
            )
            if previous != current
        )

        before = dense.state_string()
        stimulus = [value / 100.0 for value in stimulus_s100]
        dense.step(stimulus)
        sparse.step(stimulus)
        after = dense.state_string()
        if sparse.state_string() != after:
            raise TranscriptError("software sparse control diverged from dense oracle")

        changed_sites = [
            site
            for site, (left, right) in enumerate(zip(before, after))
            if left != right
        ]
        for ordinal, site in enumerate(changed_sites):
            receipts.append(
                pack_receipt(
                    logical_tick,
                    site,
                    before[site],
                    after[site],
                    stimulus_s100[site],
                    ordinal,
                )
            )

        final_phase = state_bits(after)
        final_active = mask_from_sites(scheduled)
        final_changed = mask_from_sites(changed_sites)
        final_dirty = mask_from_sites(set(sparse._dirty_next))
        previous_stimulus = list(stimulus_s100)
        stimulus_state = lfsr_step(stimulus_state)

    digests: list[dict[str, Any]] = []
    for sequence, start in enumerate(range(0, len(receipts), 10)):
        chunk = receipts[start : start + 10]
        message = canonical_message(sequence, chunk)
        digests.append(
            {
                "sequence": sequence,
                "digest": hashlib.sha256(message).digest(),
                "receipt_count": len(chunk),
            }
        )

    return {
        "accepted_ticks": 64,
        "final_phase": final_phase,
        "final_active": final_active,
        "final_changed": final_changed,
        "final_dirty": final_dirty,
        "receipt_count": len(receipts),
        "digest_count": len(digests),
        "receipts": receipts,
        "digests": digests,
    }


def frame_checksum(frame_type: int, payload: bytes) -> int:
    """Compute the one-byte fail-closed framing checksum used on the UART stream."""
    length = len(payload)
    checksum = frame_type ^ ((length >> 8) & 0xFF) ^ (length & 0xFF)
    for byte in payload:
        checksum ^= byte
    return checksum


def parse_frames(data: bytes) -> list[tuple[int, bytes]]:
    """Parse and checksum every finite CD-framed record in a transcript."""
    frames: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        if offset + 6 > len(data):
            raise TranscriptError(f"truncated frame header at offset {offset}")
        if data[offset : offset + 2] != FRAME_MAGIC:
            raise TranscriptError(f"bad frame magic at offset {offset}")
        frame_type = data[offset + 2]
        length = int.from_bytes(data[offset + 3 : offset + 5], "big")
        end = offset + 5 + length
        if end >= len(data):
            raise TranscriptError(f"truncated payload at offset {offset}")
        payload = data[offset + 5 : end]
        observed_checksum = data[end]
        expected_checksum = frame_checksum(frame_type, payload)
        if observed_checksum != expected_checksum:
            raise TranscriptError(
                f"frame checksum mismatch at offset {offset}: "
                f"got={observed_checksum:02x} expected={expected_checksum:02x}"
            )
        frames.append((frame_type, payload))
        offset = end + 1
    return frames


def verify_transcript_bytes(data: bytes) -> dict[str, Any]:
    """Require exact digest ordering and final-state equality with the oracle."""
    expected = build_expected()
    frames = parse_frames(data)
    if not frames:
        raise TranscriptError("empty transcript")

    digest_frames = [payload for kind, payload in frames if kind == FRAME_DIGEST]
    summary_frames = [payload for kind, payload in frames if kind == FRAME_SUMMARY]
    unknown = [kind for kind, _ in frames if kind not in {FRAME_DIGEST, FRAME_SUMMARY}]
    if unknown:
        raise TranscriptError(f"unknown frame types: {unknown}")
    if len(summary_frames) != 1:
        raise TranscriptError(f"expected one summary frame, got {len(summary_frames)}")
    if frames[-1][0] != FRAME_SUMMARY:
        raise TranscriptError("summary is not the terminal frame")
    if len(digest_frames) != expected["digest_count"]:
        raise TranscriptError(
            f"digest frame count mismatch: got={len(digest_frames)} "
            f"expected={expected['digest_count']}"
        )

    parsed_digests: list[dict[str, Any]] = []
    for index, (payload, oracle_row) in enumerate(
        zip(digest_frames, expected["digests"], strict=True)
    ):
        if len(payload) != 34:
            raise TranscriptError(f"digest payload {index} has length {len(payload)}")
        sequence = int.from_bytes(payload[:2], "big")
        digest = payload[2:]
        if sequence != oracle_row["sequence"]:
            raise TranscriptError(
                f"digest sequence mismatch at {index}: "
                f"got={sequence} expected={oracle_row['sequence']}"
            )
        if digest != oracle_row["digest"]:
            raise TranscriptError(f"digest bytes mismatch at sequence {sequence}")
        parsed_digests.append(
            {"sequence": sequence, "digest_hex": digest.hex()}
        )

    summary = summary_frames[0]
    if len(summary) != 51:
        raise TranscriptError(f"summary payload has length {len(summary)}")
    observed = {
        "protocol_version": summary[0],
        "profile_id": summary[1],
        "accepted_ticks": int.from_bytes(summary[2:4], "big"),
        "final_phase": int.from_bytes(summary[4:20], "big"),
        "final_active": int.from_bytes(summary[20:28], "big"),
        "final_changed": int.from_bytes(summary[28:36], "big"),
        "final_dirty": int.from_bytes(summary[36:44], "big"),
        "receipt_count": int.from_bytes(summary[44:48], "big"),
        "digest_count": int.from_bytes(summary[48:50], "big"),
        "terminal_status": summary[50],
    }
    required = {
        "protocol_version": PROTOCOL_VERSION,
        "profile_id": PROFILE_ID,
        "accepted_ticks": expected["accepted_ticks"],
        "final_phase": expected["final_phase"],
        "final_active": expected["final_active"],
        "final_changed": expected["final_changed"],
        "final_dirty": expected["final_dirty"],
        "receipt_count": expected["receipt_count"],
        "digest_count": expected["digest_count"],
        "terminal_status": TERMINAL_OK,
    }
    for key, value in required.items():
        if observed[key] != value:
            raise TranscriptError(
                f"summary mismatch for {key}: got={observed[key]} expected={value}"
            )

    return {
        "verified": True,
        "frame_count": len(frames),
        "digest_count": len(parsed_digests),
        "receipt_count": expected["receipt_count"],
        "accepted_ticks": expected["accepted_ticks"],
        "final_phase_hex": f"{expected['final_phase']:032x}",
        "final_active_hex": f"{expected['final_active']:016x}",
        "final_changed_hex": f"{expected['final_changed']:016x}",
        "final_dirty_hex": f"{expected['final_dirty']:016x}",
        "transcript_sha256": hashlib.sha256(data).hexdigest(),
        "digests": parsed_digests,
    }


def read_transcript(args: argparse.Namespace) -> bytes:
    """Read either a raw serial capture or an ASCII hexadecimal capture."""
    if args.binary_file is not None:
        return args.binary_file.read_bytes()
    if args.hex_file is not None:
        compact = "".join(args.hex_file.read_text(encoding="utf-8").split())
        try:
            return bytes.fromhex(compact)
        except ValueError as error:
            raise TranscriptError(f"invalid hexadecimal transcript: {error}") from error
    if args.hex is not None:
        try:
            return bytes.fromhex("".join(args.hex.split()))
        except ValueError as error:
            raise TranscriptError(f"invalid hexadecimal transcript: {error}") from error
    raise TranscriptError("one transcript input is required")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify a COSMIC-BOARD-01 UART transcript against the frozen oracle"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--binary-file", type=Path)
    group.add_argument("--hex-file", type=Path)
    group.add_argument("--hex")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = verify_transcript_bytes(read_transcript(args))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "COSMIC_BOARD_01_VERIFY PASS "
            f"ticks={result['accepted_ticks']} "
            f"receipts={result['receipt_count']} "
            f"digests={result['digest_count']} "
            f"transcript_sha256={result['transcript_sha256']}"
        )


if __name__ == "__main__":
    main()
