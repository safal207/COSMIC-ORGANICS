# COSMIC-HW-18 physical ULX3S handoff

COSMIC-HW-18 is the physical continuation of the exact successful HW-17
artifact. It does not rebuild or change the FPGA design. It programs the
canonical seed-1601 bitstream into volatile SRAM, captures the frozen `CO16`
UART self-test frame, and requires ten oracle-matching externally power-cycled
repetitions on one identified ULX3S-85F board.

## Frozen subject

- HW-17 head: `9d17ba05f3bb4ff4bac9c0e28d9b5842bcfbfafe`
- HW-17 run: `33313877706`, attempt 1
- result artifact: `9733436976`
- canonical seed: `1601`
- canonical bitstream SHA-256:
  `eebd73700bacdb0a29e5b5542834f150810196492218cab9b1f5c4e9158b80b3`
- canonical bitstream size: `1048738` bytes

Download `cosmic-hw-17-result` from the frozen workflow run and extract
`cosmic_hw_17_canonical.bit`. Verify it without touching hardware:

```bash
python tools/cosmic_hw_18_hil.py verify-bitstream \
  --bitstream /absolute/path/cosmic_hw_17_canonical.bit
```

This command intentionally returns a non-zero process status and
`BOARD_NOT_AVAILABLE`: byte identity alone is not physical execution.

## Rig contract

The physical host must be Linux and have:

- the identified ULX3S-85F connected through US1;
- a stable serial path, preferably `/dev/serial/by-id/...`;
- either `openFPGALoader` or `fujprog`;
- an executable external power-cycle hook;
- at least one photo or video file showing the board/rig.

The hook is invoked without a shell as:

```text
HOOK REPETITION_NUMBER REPETITION_EVIDENCE_DIRECTORY
```

It must perform a real power-off/power-on cycle and return zero only after the
board can begin USB enumeration. The harness records the hook binary hash and
its output, but operator-provided identity and physical behavior remain an
attestation boundary.

Persistent flash writes are forbidden. Each repetition uses only one of these
frozen volatile-SRAM commands:

```text
openFPGALoader -b ulx3s BITSTREAM
fujprog BITSTREAM
```

## Execute the frozen ten-repetition run

Run from a clean committed checkout and write evidence outside the repository:

```bash
python tools/cosmic_hw_18_hil.py run \
  --bitstream /absolute/path/cosmic_hw_17_canonical.bit \
  --serial-port /dev/serial/by-id/YOUR_ULX3S_PORT \
  --programmer openFPGALoader \
  --power-cycle-hook /absolute/path/cold_cycle_ulx3s \
  --output-dir /absolute/path/cosmic-hw-18-evidence \
  --media /absolute/path/rig-photo.jpg \
  --operator "OPERATOR NAME" \
  --board-id "BOARD SERIAL OR ASSET ID" \
  --board-revision "ULX3S PCB REVISION" \
  --fpga-marking "LFE5U-85F-6BG381C" \
  --confirm-volatile-sram-programming
```

The run stops at the first failed repetition and emits one of the frozen
failure decisions. A green `ULX3S_PROOF_EDGE_HIL_SUPPORTED` result requires
10/10 repetitions, the exact bitstream, a clean harness checkout, successful
external cold cycling and volatile programming, a raw capture and verifier JSON
for every repetition, exact oracle equality with zero error flags, and copied
photo/video evidence. The harness copies the canonical subject into the evidence
directory, makes it read-only, and rechecks its size and SHA-256 after every
power cycle immediately before programming. The evidence directory must be
outside the repository checkout.

## Claim boundary

A green result supports execution of this exact self-test and bitstream on the
one recorded physical board and rig. It is not a CPU comparison. Power, energy,
thermal behavior, throughput under live ingress, p99 latency and an optimized
native CPU baseline require separate measured experiments.
