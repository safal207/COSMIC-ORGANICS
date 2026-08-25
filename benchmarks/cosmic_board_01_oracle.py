from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path


PROTOCOL = "COSMIC-BOARD-01/v0.1"
CELLS = 64
TICKS = 64
MASK512 = (1 << 512) - 1
INITIAL_STIMULUS_HEX = (
    "1f123bb5a55a0f0fc33ca5a56969f00fd15ea5e5c001d00dcafe5eed12345678"
    "89abcdef0123456776543210fedcba98a5a55a5ac3c33c3cf0f00f0f55aa55aa"
)
LFSR_TAPS = (511, 509, 503, 500)

PHASE_A = 0
PHASE_M = 1
PHASE_C = 2

FRAME_SYNC = b"CO"
FRAME_START = 0x01
FRAME_DIGEST = 0x20
FRAME_END = 0x7F
TERMINAL_SUCCESS = 0xA5

FROZEN_EXPECTED = {
    "initial_stimulus_hex": INITIAL_STIMULUS_HEX,
    "lfsr_taps": list(LFSR_TAPS),
    "stimulus_stream_sha256": "b487eb56926751feeea59b8073c4c980c3ad2daf0f46e2bca84f849e6afb9546",
    "tick_observation_sha256": "a4d890ab7bdff9e1def00580af50d466dadcf3a94ca8833fd4c05517ac1d20d5",
    "receipt_count": 2765,
    "receipt_stream_sha256": "1253c4b78649cd7dfdbdf243fe6b4481db417d5339e4b8577d331841edc673ab",
    "digest_count": 277,
    "digest_stream_sha256": "0af0bf873d1af7a50f9333236160073f80951d8a5d947e457af6f6bc20126397",
    "final_partial_receipt_count": 5,
    "first_digest_hex": "a38c0b9d5b1503f66b0e24c598ff41bc1d48dc3f5fb41f97e54d5842545eae13",
    "last_digest_hex": "364fadb92dc4abc21eba864dc98fd264a74b629b5e7a30516e26661f08b1fee2",
    "final_phase_hex": "89599564652990111a999542a4056896",
    "final_active_hex": "ffffffffffffffff",
    "final_changed_hex": "7d7b7f57577fa7ff",
    "final_dirty_hex": "ffffffffffffffff",
    "uart_frame_count": 279,
    "uart_transcript_bytes": 11711,
    "uart_transcript_sha256": "1304a940c94180db5e6713964cdea9930da8cf2f297afcaf8c2e897e22588d58",
}


def _signed8(value: int) -> int:
    value &= 0xFF
    return value - 256 if value >= 128 else value


def _neighbors(site: int) -> tuple[int, ...]:
    row, col = divmod(site, 8)
    result: list[int] = []
    if row > 0:
        result.append(site - 8)
    if row < 7:
        result.append(site + 8)
    if col > 0:
        result.append(site - 1)
    if col < 7:
        result.append(site + 1)
    return tuple(result)


def _phase_bus(phases: list[int]) -> int:
    value = 0
    for site, phase in enumerate(phases):
        value |= (phase & 0x3) << (2 * site)
    return value


def _next_lfsr(value: int) -> int:
    feedback = 0
    for tap in LFSR_TAPS:
        feedback ^= (value >> tap) & 1
    return ((value << 1) & MASK512) | feedback


def _pack_receipt(
    logical_tick: int,
    site: int,
    phase_before: int,
    phase_after: int,
    stimulus_s100: int,
    ordinal: int,
) -> int:
    return (
        ((logical_tick & 0xFFFF) << 24)
        | ((site & 0x3F) << 18)
        | ((phase_before & 0x3) << 16)
        | ((phase_after & 0x3) << 14)
        | ((stimulus_s100 & 0xFF) << 6)
        | (ordinal & 0x3F)
    )


def _crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _frame(frame_type: int, record_sequence: int, payload: bytes) -> bytes:
    if not 0 <= len(payload) <= 255:
        raise ValueError("payload length outside one-byte protocol range")
    body = (
        bytes((frame_type, len(payload)))
        + record_sequence.to_bytes(2, "big")
        + payload
    )
    return FRAME_SYNC + body + _crc16_ccitt_false(body).to_bytes(2, "big")


def _commitments(receipts: list[int]) -> list[dict]:
    result: list[dict] = []
    for sequence, offset in enumerate(range(0, len(receipts), 10)):
        real = receipts[offset : offset + 10]
        count = len(real)
        domain = 0x434F if count == 10 else (0x4340 | count)
        slots = real + [0] * (10 - count)
        message = (
            domain.to_bytes(2, "big")
            + sequence.to_bytes(2, "big")
            + b"".join(receipt.to_bytes(5, "big") for receipt in slots)
        )
        if len(message) != 54:
            raise RuntimeError("canonical commitment message is not 54 bytes")
        result.append(
            {
                "sequence": sequence,
                "real_receipt_count": count,
                "digest": sha256(message).digest(),
                "message": message,
            }
        )
    return result


def build_oracle() -> dict:
    phases = [PHASE_A] * CELLS
    previous_stimulus = [0] * CELLS
    dirty_mask = 0
    stimulus_state = int(INITIAL_STIMULUS_HEX, 16)

    stimulus_stream = bytearray()
    ticks: list[dict] = []
    receipts: list[int] = []

    for logical_tick in range(1, TICKS + 1):
        stimuli = [
            _signed8((stimulus_state >> (8 * site)) & 0xFF)
            for site in range(CELLS)
        ]
        stimulus_stream.extend(value & 0xFF for value in stimuli)

        active_mask = 0
        next_phases = phases.copy()
        changed_mask = 0

        for site in range(CELLS):
            stimulus = stimuli[site]
            active = bool((dirty_mask >> site) & 1) or (
                stimulus != previous_stimulus[site]
            )
            if not active:
                continue

            active_mask |= 1 << site
            row, col = divmod(site, 8)
            neighbors = _neighbors(site)
            neighbor_count = len(neighbors)
            neighbor_sum2 = sum(phases[item] for item in neighbors)
            self_value2 = phases[site]
            delta_phase2 = neighbor_sum2 - neighbor_count * self_value2
            coupling100 = 75 if (row + col) % 2 == 0 else 50

            if phases[site] == PHASE_M:
                threshold100 = 5
            elif (row + col) % 2 == 0:
                threshold100 = 50
            else:
                threshold100 = 35

            drive_num = (
                2 * neighbor_count * stimulus
                + coupling100 * delta_phase2
            )
            limit = 2 * neighbor_count * threshold100

            if drive_num >= limit:
                next_phases[site] = min(PHASE_C, phases[site] + 1)
            elif drive_num <= -limit:
                next_phases[site] = max(PHASE_A, phases[site] - 1)

            if next_phases[site] != phases[site]:
                changed_mask |= 1 << site

        next_dirty = 0
        changed_sites = [
            site for site in range(CELLS) if (changed_mask >> site) & 1
        ]
        for ordinal, site in enumerate(changed_sites):
            next_dirty |= 1 << site
            for item in _neighbors(site):
                next_dirty |= 1 << item
            receipts.append(
                _pack_receipt(
                    logical_tick,
                    site,
                    phases[site],
                    next_phases[site],
                    stimuli[site],
                    ordinal,
                )
            )

        phases = next_phases
        previous_stimulus = stimuli
        dirty_mask = next_dirty
        ticks.append(
            {
                "tick": logical_tick,
                "stimulus": stimulus_state,
                "phase": _phase_bus(phases),
                "active": active_mask,
                "changed": changed_mask,
                "dirty": dirty_mask,
            }
        )
        stimulus_state = _next_lfsr(stimulus_state)

    commitments = _commitments(receipts)

    tick_observations = b"".join(
        row["phase"].to_bytes(16, "big")
        + row["active"].to_bytes(8, "big")
        + row["changed"].to_bytes(8, "big")
        + row["dirty"].to_bytes(8, "big")
        for row in ticks
    )
    receipt_stream = b"".join(
        receipt.to_bytes(5, "big") for receipt in receipts
    )
    digest_stream = b"".join(
        row["sequence"].to_bytes(2, "big") + row["digest"]
        for row in commitments
    )

    frames: list[bytes] = []
    record_sequence = 0
    start_payload = (
        (1).to_bytes(2, "big")
        + b"PES1"
        + TICKS.to_bytes(2, "big")
        + b"L512"
    )
    frames.append(_frame(FRAME_START, record_sequence, start_payload))
    record_sequence += 1

    for row in commitments:
        payload = row["sequence"].to_bytes(2, "big") + row["digest"]
        frames.append(_frame(FRAME_DIGEST, record_sequence, payload))
        record_sequence += 1

    final = ticks[-1]
    end_payload = (
        bytes((TERMINAL_SUCCESS,))
        + TICKS.to_bytes(2, "big")
        + len(receipts).to_bytes(4, "big")
        + len(commitments).to_bytes(2, "big")
        + final["phase"].to_bytes(16, "big")
        + final["active"].to_bytes(8, "big")
        + final["changed"].to_bytes(8, "big")
        + final["dirty"].to_bytes(8, "big")
    )
    frames.append(_frame(FRAME_END, record_sequence, end_payload))
    transcript = b"".join(frames)

    summary = {
        "protocol": PROTOCOL,
        "ticks": TICKS,
        "initial_stimulus_hex": INITIAL_STIMULUS_HEX,
        "lfsr_taps": list(LFSR_TAPS),
        "stimulus_stream_sha256": sha256(stimulus_stream).hexdigest(),
        "tick_observation_sha256": sha256(tick_observations).hexdigest(),
        "receipt_count": len(receipts),
        "receipt_stream_sha256": sha256(receipt_stream).hexdigest(),
        "digest_count": len(commitments),
        "digest_stream_sha256": sha256(digest_stream).hexdigest(),
        "final_partial_receipt_count": commitments[-1][
            "real_receipt_count"
        ],
        "first_digest_hex": commitments[0]["digest"].hex(),
        "last_digest_hex": commitments[-1]["digest"].hex(),
        "final_phase_hex": f"{final['phase']:032x}",
        "final_active_hex": f"{final['active']:016x}",
        "final_changed_hex": f"{final['changed']:016x}",
        "final_dirty_hex": f"{final['dirty']:016x}",
        "uart_frame_count": len(frames),
        "uart_transcript_bytes": len(transcript),
        "uart_transcript_sha256": sha256(transcript).hexdigest(),
    }

    if summary != {"protocol": PROTOCOL, "ticks": TICKS, **FROZEN_EXPECTED}:
        raise RuntimeError(
            "BOARD-01 oracle moved:\n"
            + json.dumps(summary, indent=2, sort_keys=True)
        )

    return {
        "summary": summary,
        "ticks": ticks,
        "receipts": receipts,
        "commitments": [
            {
                "sequence": row["sequence"],
                "real_receipt_count": row["real_receipt_count"],
                "digest_hex": row["digest"].hex(),
            }
            for row in commitments
        ],
        "transcript": transcript,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-transcript", type=Path)
    args = parser.parse_args()

    oracle = build_oracle()
    if args.write_transcript is not None:
        args.write_transcript.write_bytes(oracle["transcript"])
    if args.json:
        print(json.dumps(oracle["summary"], indent=2, sort_keys=True))
    else:
        print(
            "COSMIC_BOARD_01_ORACLE PASS "
            f"ticks={oracle['summary']['ticks']} "
            f"receipts={oracle['summary']['receipt_count']} "
            f"digests={oracle['summary']['digest_count']} "
            f"transcript_sha256={oracle['summary']['uart_transcript_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
