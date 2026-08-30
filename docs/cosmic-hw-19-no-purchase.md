# COSMIC-HW-19: no-purchase CPU comparison and remote HIL

## Outcome

HW-19 removes board ownership from the critical path without pretending that
simulation is physical evidence. It creates two independent evidence lanes:

1. a real, optimized, single-thread CPU measurement of the exact HW-16 self-test;
2. a one-command wrapper that lets an independent ULX3S-85F owner execute the
   frozen HW-18 physical protocol and return a SHA-256-bound archive.

The FPGA number emitted before that remote run is a cycle model, not a physical
measurement and not a superiority claim.

## Same-work contract

One operation is exactly:

- 64 cells, initially `A`;
- two accepted ticks with `stimulus_s100 = +100`;
- all cells transition `A -> M -> C`;
- 128 ordered 40-bit receipts;
- twelve full 10-receipt SHA-256 commitments;
- one final 8-receipt partial commitment;
- final digest
  `c31bff9259318b3309bdb0fdd5282ce58366d6d8d1b9c636080eb6482a230ab2`.

The CPU implementation performs the transition law, receipt construction,
commitment assembly, and all thirteen SHA-256 operations on every timed
iteration. It uses the host OpenSSL implementation and records the CPU,
compiler, OpenSSL version, affinity, sample count, warmup, mean, median, and
single-operation p99. The stimulus is read through a volatile runtime input so
the compiler cannot replace the transition and receipt path with a constant.

## Run the software comparison

Prerequisites are `g++`, OpenSSL development headers, `iverilog`, and `vvp`.

```bash
python tools/cosmic_hw_19_compare.py --output /tmp/cosmic-hw-19.json
```

The result must say:

- `CPU_BASELINE_MEASURED_FPGA_MODELED_PHYSICAL_NOT_RUN`;
- `physical_execution_state: NOT_RUN`;
- `competitive_claim_allowed: false`.

The model counts exact RTL cycles from reset release until all thirteen digests
retire and the self-test enters `ST_CHECKSUM`. UART transmission and evidence
transport are excluded. Both the configured 10 MHz point and the canonical
seed's routed 20.25 MHz Fmax point are labeled non-physical.

## Remote board run without buying hardware

The remote operator checks out the exact published HW-19 revision, copies
`docs/cosmic-hw-19-operator.example.json` outside the repository, fills in the
real paths and board identity, and runs:

```bash
python tools/cosmic_hw_19_remote_run.py --config /absolute/path/operator.json
```

The command delegates to HW-18. It verifies the canonical bitstream SHA and
size, permits only volatile SRAM programming, performs ten external cold power
cycles, verifies every CO16 UART oracle, captures media and raw evidence, then
creates `OUTPUT_DIR.tar.gz` and `OUTPUT_DIR.tar.gz.sha256` next to the evidence
directory. Persistent flash remains forbidden.

The operator needs the ULX3S-85F, a stable serial device path, either
`openFPGALoader` or `fujprog`, an executable external power-cycle hook, and at
least one rig photo or video. The project owner does not need to purchase the
board.

## Honest boundary

HW-19 does not yet add a live external workload ingress to the frozen HW-17
bitstream. Changing the RTL or bitstream would create a new experimental
subject and must be preregistered separately. A physical CPU-versus-FPGA claim
also needs on-board timing and power instrumentation; the current CO16 frame
proves correctness, not elapsed compute time or energy.
