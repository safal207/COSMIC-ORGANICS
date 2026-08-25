# Architecture Review Surface

This note is for FPGA, computer-architecture, formal-verification, and trustworthy-systems collaborators. It describes what should be reviewed next and what is already frozen.

## System boundary

```text
authoritative execution
-----------------------
stimulus
  -> lattice state
  -> sparse scheduler
  -> transition law
  -> synchronous commit

observational evidence
----------------------
committed transition
  -> receipt
  -> SHA commitment
  -> Merkle root / inclusion path
  -> HMAC-authenticated root
```

Evidence may create finite backpressure before later work is accepted. Evidence contents do not influence the transition law, dirty-frontier membership, or committed state.

## Frozen semantic invariants

1. Dense and sparse execution produce identical state and transition counts on the frozen workload.
2. Receipts are ordered, deterministic, and contain no missing, duplicate, or phantom transition.
3. Each real receipt is covered exactly once by the commitment stream.
4. Merkle roots and proof fragments match the frozen Python oracle.
5. Every real-leaf inclusion proof independently recomputes its emitted root.
6. HMAC tags bind the root to source sequence, tree ordinal, and real-leaf count.
7. Proof/HMAC state has no authority path into A/M/C execution.
8. Negative results and measurement-harness failures are retained rather than overwritten.

## Current physical boundary

The exact FULL-PROOF stack did not fit `LFE5U-85F-8BG381C`:

- 116,535 / 83,640 `TRELLIS_COMB` — 139%;
- 201 / 156 `MULT18X18D` — 128%;
- 29,407 / 83,640 FF — 35%;
- 0 / 208 EBR.

All five preregistered seeds reached the same capacity class before useful routing. No full-stack Fmax was measured.

## Questions for review

### 1. Scheduler locality

- Can the 64-bit centralized dirty mask become per-tile local queues without changing synchronous semantics?
- What is the minimum halo exchange needed for exact von-Neumann dependencies?
- Would a hierarchical frontier reduce wire length and fanout enough to justify extra control?
- How should duplicate work be suppressed across tile boundaries?

### 2. Receipt memory organization

- Can the 848-bit batch snapshots move into EBR/BRAM without worsening deterministic ordering?
- Is storing complete pre/post snapshots necessary, or can receipts be generated from smaller per-transition records?
- Can serialization and execution be decoupled with a bounded ring buffer whose overflow behavior is explicit?
- Which metadata must remain in FFs for timing?

### 3. Proof cost and disclosure policy

- Should the hardware commit every receipt but generate inclusion proofs only on demand?
- Can internal nodes be recomputed from persisted leaves instead of retained for every tree?
- Is Merkle-16 the right tree width for the selected storage and disclosure workload?
- Can proof fragments be streamed directly to memory rather than held in fabric?
- What proof sampling/incident policy gives a defensible audit guarantee?

### 4. Crypto resource sharing

- Can leaf SHA, Merkle SHA, and HMAC share one or two iterative compression engines through a deterministic scheduler?
- What throughput loss results under the actual buyer workload?
- Can precomputed HMAC ipad/opad states reduce area without weakening the measurement boundary?
- Which operations should move to a host CPU or secure element?

### 5. Physical feasibility

- Which FPGA family is justified by the selected profile rather than by the desire to fit the largest prototype?
- What successful post-route clock target is meaningful for the application?
- Which signals need board-level observability?
- What clock-gating or operand-isolation strategy can convert fewer PE evaluations into measurable energy savings?
- What is the smallest board experiment that can measure joules per accepted transition honestly?

### 6. Security boundary

- How are keys provisioned, rotated, and isolated?
- What external root of trust signs or anchors authenticated roots?
- What fault-injection and side-channel assumptions are acceptable?
- How does the verifier bind sensor/input provenance to the committed transition?

## Requested review output

A useful collaborator review should return:

1. the preferred product profile: CORE, AUDIT, or FULL-PROOF;
2. the top three area/timing blockers;
3. one proposed memory map;
4. one proposed scheduler topology;
5. one explicit threat model;
6. a falsifiable next experiment with fixed target, workload, metrics, and stop rule.

## Evidence entry points

- Integrated software kernel: PR [#69](https://github.com/safal207/COSMIC-ORGANICS/pull/69)
- Sparse RTL: PR [#72](https://github.com/safal207/COSMIC-ORGANICS/pull/72)
- Receipt pipeline: PR [#75](https://github.com/safal207/COSMIC-ORGANICS/pull/75)
- SHA throughput: PR [#84](https://github.com/safal207/COSMIC-ORGANICS/pull/84)
- Merkle proofs: PR [#88](https://github.com/safal207/COSMIC-ORGANICS/pull/88)
- Merkle frontier: PR [#91](https://github.com/safal207/COSMIC-ORGANICS/pull/91)
- HMAC roots: PR [#94](https://github.com/safal207/COSMIC-ORGANICS/pull/94)
- ECP5 capacity boundary: PR [#97](https://github.com/safal207/COSMIC-ORGANICS/pull/97)
- Verified application demo: PR [#99](https://github.com/safal207/COSMIC-ORGANICS/pull/99)
