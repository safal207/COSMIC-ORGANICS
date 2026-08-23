# COSMIC-HW-07/v0.1 — Transition-receipt RTL cost

## Status

Preregistered before `rtl/cosmic_hw_07_receipt.v` exists.

Parent hardware result: COSMIC-HW-06 Phase 1 GREEN at `5b3b4c8c77ffdbe17ad573951cca59a1c15aeb44`.

The purpose of HW-07 is to measure the hardware cost of observing and exporting committed lattice transitions. It is **not** a cryptographic-proof experiment: no SHA/Merkle engine is instantiated in v0.1.

## Receipt record

Exactly 40 bits per emitted transition:

| Bits | Field |
| --- | --- |
| `[39:24]` | `logical_tick` (16-bit unsigned, committed tick numbering starts at 1) |
| `[23:18]` | `site_id` (0..63) |
| `[17:16]` | `phase_before` (`A=00`, `M=01`, `C=10`) |
| `[15:14]` | `phase_after` |
| `[13:6]` | signed `stimulus_s100` |
| `[5:0]` | `ordinal_in_batch`, starting at 0 |

Receipts within one committed tick are serialized in ascending `site_id` order. `ordinal_in_batch` must therefore equal the transition's zero-based rank among set bits of the committed `changed_mask`.

## Batch snapshot

The observer stores enough information to serialize receipts after the authoritative state update:

```text
logical_tick        16 bits
changed_mask        64 bits
pre_phase_state    128 bits
post_phase_state   128 bits
stimulus_bus       512 bits
---------------------------
                    848 bits / batch
```

The v0.1 queue depth is **4 batches**. This is a deliberately finite resource, not an infinite-model convenience.

## Reservation / backpressure rule

A new logical tick may be accepted only when one batch slot can be reserved for its future commit observation.

```text
tick_accept = tick_valid && tick_ready
```

Rules:

1. reservation occurs before authoritative tick commit;
2. the transition engine is never partially committed and then cancelled because of receipt pressure;
3. after commit, a zero-transition tick releases its reservation without enqueuing a batch;
4. a non-zero transition tick converts its reservation into a queued 848-bit batch;
5. the serializer consumes the oldest queued batch;
6. `receipt_ready=0` holds the current receipt stable and may eventually create tick backpressure;
7. no receipt may be dropped, overwritten, duplicated or synthesized without a committed transition;
8. the receipt path has no signal into next-state arithmetic or sparse dirty-frontier generation except the pre-commit `tick_ready` admission boundary.

This reservation model intentionally exposes finite-buffer pressure instead of assuming that observation is free.

## Output interface

One receipt lane:

```text
receipt_valid
receipt_ready
receipt_data[39:0]
```

The lane emits at most one transition receipt per physical cycle.

This is intentionally narrow. If high-transition workloads stall badly, that is a valid v0.1 result and motivates a later width/batching experiment. Do not widen the lane after seeing results.

## Compared systems

- `DENSE_MESH_64` — frozen HW-06 dense control.
- `SPARSE_MESH_64` — frozen HW-06 sparse control.
- `DENSE_MESH_64_RECEIPT` — same dense engine plus the exact generic observer above.
- `SPARSE_MESH_64_RECEIPT` — same sparse engine plus the same observer.

Receipt semantics and queue organization are identical for dense and sparse receipt systems.

## Workloads

### Paired Phase 1 corpus

Reuse exact HW-06 vectors:

- 256 sequences;
- 12 logical ticks each;
- 1%, 5%, 20%, 100% activity;
- same initial state and stimuli.

This preserves paired execution-cost attribution.

### Receipt-stress corpus

Freeze at least 64 additional sequences before receipt RTL.

Required classes:

- all-64 transition tick;
- adjacent/colliding clusters;
- alternating high/low transition bursts;
- back-to-back transition-heavy ticks;
- zero-transition ticks.

Consumer readiness patterns are also frozen before RTL:

```text
always_ready              cycle % 1 -> ready
three_ready_one_blocked   cycle % 4 != 3
alternating_ready_blocked cycle % 2 == 0
eight_cycle_block_bursts  cycle % 16 >= 8
```

A stimulus for a not-yet-accepted logical tick must remain stable while `tick_valid=1 && tick_ready=0`.

## Functional oracle

For every accepted tick:

- receipt-enabled phase state == corresponding no-receipt phase state;
- transition count identical;
- changed mask identical;
- sparse active and dirty masks identical;
- emitted receipt count == population count of all committed changed masks;
- exact record contents match the software transition oracle;
- ordering is deterministic ascending site;
- zero missing / duplicate / phantom receipts;
- receipt replay reconstructs the committed transition trace;
- no execution-semantic contamination.

## Primary cost dimensions

Do not collapse these into one score.

### Execution

- PE evaluations;
- state writes;
- accepted logical ticks;
- physical cycles;
- `tick_ready=0` cycles while a tick is pending;
- number of receipt-induced backpressure events.

### Receipt

- records emitted;
- fixed 40 bits / record;
- serializer cycles;
- batch queue pushes/pops;
- maximum occupied/reserved slots;
- output-ready blocked cycles;
- queue-pressure stall cycles.

### Structural synthesis

Measure each of all four tops after hierarchy flattening before Xilinx-7 mapping:

- LUT;
- FF;
- BRAM;
- LUTRAM;
- core cells excluding top-level I/O;
- logic-depth proxy;
- architectural state bits;
- receipt/buffer logical bits.

Report deltas, not just absolute values:

```text
dense+receipt - dense
sparse+receipt - sparse
sparse+receipt - dense+receipt
```

## Decision

`CONTROL_FAILURE`
: frozen HW-06 semantics or baseline no-receipt controls regress.

`RECEIPT_SEMANTICS_NOT_PRESERVED`
: receipt observation changes execution semantics or receipt correctness is <100%.

`RECEIPT_COST_DOMINATES_REFERENCE_DESIGN`
: semantics pass, but the finite single-lane receipt design introduces severe explicitly reported structural/backpressure cost. This is a descriptive architecture outcome, not a hidden composite threshold; all dimensions must be shown separately.

`SPARSE_PLUS_RECEIPT_PARETO_SUPPORTED`
: semantics and receipt correctness are 100%, the sparse receipt system retains >=50% PE-evaluation reduction at 1% and 5% activity, and measured receipt costs are reported separately without an arbitrary combined score.

No decision may be based on Python or wall-clock timing alone.

## Deferred boundary

HW-08 should test a real commitment/hash engine separately. A receipt containing transition facts is not by itself a cryptographic proof.

No claim here about post-route Fmax, board power, energy, thermal behavior, ASIC PPA, CPU/GPU superiority, cryptographic proof completeness, quantum computing or lattice QCD.
