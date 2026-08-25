# COSMIC ORGANICS — Research Status

This document is the release-level evidence matrix for `COSMIC-RELEASE-01`. It separates supported mechanisms, negative results, and open product risks. Historical draft PRs and frozen branches remain the canonical provenance record.

## Immutable release boundary

- Frozen full-stack source/result: `773b68597b9136c12867ecc1a3a1749edcba1627`
- Frozen branch: `research/cosmic-hw-13-frozen-result`
- Application-demo head: `39aa1f9b4d16bf33f7ce48be34000cad7ae3494b`
- Consolidation branch: `release/cosmic-research-v0.1`

The consolidation branch adds release documentation, a focused CI surface, and the verified demo. It does not rewrite frozen benchmark outcomes.

## Evidence matrix

| Experiment | Exact result head | Hosted run | Decision | What the evidence supports |
|---|---|---:|---|---|
| BARDO-FRONTIER-02 | `2021c7ea03519f58c30e37c6e720b6a1db4e4d32` | hosted Python 3.11/3.12 evidence in [#59](https://github.com/safal207/COSMIC-ORGANICS/issues/59) | `SPARSE_EXECUTION_VALUE_ONLY` | Strong sparse scheduling is valuable; a Bardo-labelled relation frontier gave **0%** node-evaluation advantage over the dirty-node control. |
| COSMIC-KERNEL-05 | `8e7e040eb305619c459e0caf66225a4c6a1e3f9c` | hosted Python 3.11/3.12 evidence in [#67](https://github.com/safal207/COSMIC-ORGANICS/issues/67) | `SPARSE_PLUS_PROOF_PARETO_SUPPORTED` | Sparse execution retained exact state/transition semantics while an observational committed-proof layer accepted valid proofs and rejected frozen mutation families. |
| COSMIC-HW-06 | `5b3b4c8c77ffdbe17ad573951cca59a1c15aeb44` | `32611039523` | `SPARSE_RTL_VALUE_SUPPORTED` | 64-PE dense/sparse RTL equivalence; PE-evaluation reductions of 95.54%, 86.69%, 54.99%, and 16.67% at 1%, 5%, 20%, and 100% activity. |
| COSMIC-HW-07 | `1e71648e1a2f375d7eeb3147a301a81dc8bc2399` | `32616215084` | `SPARSE_PLUS_RECEIPT_PARETO_SUPPORTED` | 41,144 exact deterministic transition receipts with zero missing, duplicate, or phantom records; receipt implementation cost is substantial. |
| COSMIC-HW-07B | `9ad5b01b9960a49f4800dbffcdf96b4dac50bd6e` | `32616773253` | `NO_VALID_MICROARCHITECTURE_IMPROVEMENT` | Hierarchical selection reduced depth, smaller FIFOs reduced state, but no candidate replaced the frozen control under the preregistered cost/backpressure rule. |
| COSMIC-HW-08 | `84e1bbc8cd7cb42fba8e7f4de736ebf48161307d` | `32621848565` | `SHA256_COMMITMENT_COST_MEASURED` | 130/130 SHA KATs; 41,144 receipts committed exactly once into 4,240 ordered SHA-256 digests. One engine is a throughput bottleneck. |
| COSMIC-HW-09 | `2cbc6442ff81f49ff6e247ffc5552ca2efa54c3d` | `32623113733` | `SHA_THROUGHPUT_VALUE_SUPPORTED` | SHA256x2 and x4 reduced moderate/high-density stalls; preregistered cost-first handoff selected x2. |
| COSMIC-HW-10 | `fb855d03093813e21bc751ff8051ce5c9f0b861f` | `32624292338` | `MERKLE_INCLUSION_COST_MEASURED` | 4,240 leaves, 444 exact roots, 16,960 proof fragments, and 4,240/4,240 independently verified inclusion proofs; baseline is expensive. |
| COSMIC-HW-11 | `1ed75676e59a7a745ace852c8b24982dfb41a614` | `32626162443` | `MERKLE_THROUGHPUT_VALUE_SUPPORTED` | Two Merkle SHA engines reduced total cycles by 39.23%; cost-first rule selected `B1_M2` rather than the faster but larger `B2_M2`. |
| COSMIC-HW-12 | `7bad7ba095c65221e057696df40fcd6c53dee2b8` | `32634697011` | `HMAC_ROOT_AUTH_COST_MEASURED` | 444/444 roots received exact HMAC-SHA256 tags with exact root/metadata association; no added tick stalls, but roughly 22% more mapped core cells. |
| COSMIC-HW-13 | `773b68597b9136c12867ecc1a3a1749edcba1627` | `32853523449` | `DEVICE_CAPACITY_NOT_SUPPORTED` | Exact full stack preserved through ECP5 synthesis/harness smoke, but did not fit `LFE5U-85F-8BG381C`: 139% combinational and 128% multiplier utilization. |
| VERIFIED-INCIDENT-DEMO | `39aa1f9b4d16bf33f7ce48be34000cad7ae3494b` | `32855291571` | `PASS` | 16×16 localized incident workload; 40/40 audited transitions; exact dense/sparse replay; mutation rejection; 97.3307% node-evaluation reduction. |

Canonical PRs: [#61](https://github.com/safal207/COSMIC-ORGANICS/pull/61), [#69](https://github.com/safal207/COSMIC-ORGANICS/pull/69), [#72](https://github.com/safal207/COSMIC-ORGANICS/pull/72), [#75](https://github.com/safal207/COSMIC-ORGANICS/pull/75), [#78](https://github.com/safal207/COSMIC-ORGANICS/pull/78), [#81](https://github.com/safal207/COSMIC-ORGANICS/pull/81), [#84](https://github.com/safal207/COSMIC-ORGANICS/pull/84), [#88](https://github.com/safal207/COSMIC-ORGANICS/pull/88), [#91](https://github.com/safal207/COSMIC-ORGANICS/pull/91), [#94](https://github.com/safal207/COSMIC-ORGANICS/pull/94), [#97](https://github.com/safal207/COSMIC-ORGANICS/pull/97), and [#99](https://github.com/safal207/COSMIC-ORGANICS/pull/99).

## Supported statements

1. A strong dirty-frontier scheduler can preserve the frozen lattice semantics while reducing node/PE evaluations on sparse workloads.
2. Completed local transitions can be bound to a committed pre-state and verified with disclosed local facts and causal parents.
3. The software proof observer can remain outside transition authority.
4. Deterministic receipts, SHA commitments, Merkle paths, and HMAC-authenticated roots can be implemented as synthesizable RTL with exact frozen-oracle agreement.
5. The full proof stack is too large for the preregistered ECP5-85F implementation as currently organized.

## Falsified or narrowed statements

1. **No Bardo-specific scheduler advantage.** The value belongs to strong sparse execution.
2. **No Bardo-specific proof-compression advantage.** The value belongs to generic committed causal graphs.
3. **No unique buffering/SHA claim.** These are conventional implementation mechanisms.
4. **No energy claim.** Reduced enabled work is an opportunity for later clock/power-gating measurement, not a watt result.
5. **No universal processor claim.** Results are workload- and implementation-bound.
6. **No lattice-QCD equivalence.** Both use lattices, but the semantics and scientific purpose differ.
7. **No public non-repudiation.** HW-12 uses HMAC with a public deterministic test key for cost/correctness measurement.

## Readiness assessment

These percentages are engineering estimates, not benchmark outputs:

| Layer | Readiness | Meaning |
|---|---:|---|
| Reproducible software research kernel | **85%** | Deterministic implementation, controls, proofs, mutation checks, and demo exist. API/product ergonomics remain immature. |
| Application demo / collaborator entry point | **90%** | Reproducible, CI-backed, and traceable; only one domain workload is demonstrated. |
| Synthesizable RTL semantics | **75%** | Major chain is implemented and oracle-checked; resource organization is still research-grade. |
| Full proof stack on ECP5-85F | **0% fit** | The exact frozen design exceeds device capacity. This says nothing about smaller profiles or larger devices. |
| Hardware product architecture | **40%** | Interfaces and costs are known; memory hierarchy, resource sharing, target device, and workload profile are unresolved. |
| Production processor / silicon | **10–15%** | No board execution, power, placed/routed full-stack Fmax, secure key lifecycle, ASIC flow, or manufacturing evidence. |
| External research package | **80% after release merge** | Code, demo, evidence matrix, honest negative results, and review questions are consolidated. |

## Open risks

### Architecture

- The centralized scheduler may not scale physically without locality or hierarchy.
- Receipt snapshots and proof state use too much FF/LUT fabric; BRAM-oriented organization is untested.
- Full disclosure proofs are large: the incident demo produced a 77,666-byte canonical proof payload for 40 transitions.
- The current tree/proof pipeline retains every inclusion fragment; customer workflows may need selective disclosure instead.

### Security

- HMAC key provisioning, rotation, storage, side-channel behavior, and fault resistance are untested.
- No public-key signature or external timestamp/anchor is implemented.
- Proof validity does not by itself establish that an external sensor or input source was honest.

### Physical implementation

- No full-stack device fit exists on ECP5-85F.
- No placed-and-routed Fmax exists for a successful full-stack implementation.
- No board power or joules-per-transition measurements exist.
- Xilinx-7 numbers are structural mapping proxies, not device utilization or timing closure.

### Product

- The first valuable customer surface is likely an **audit profile**, not a universal processor.
- Proof policy must be explicit: every transition, sampled transitions, incident-triggered proof, or off-core proof construction.
- A buyer-specific workload must be frozen before any new performance claim.

## Next admitted work

The stop rule remains active: do not create HW-14 merely to continue numbering.

Admitted next steps are:

1. merge the consolidation release after focused CI passes;
2. obtain an external architecture review;
3. select one product profile and one buyer workload;
4. only then preregister a blocker-specific hardware experiment, such as BRAM-backed receipts, shared crypto, smaller lattice, or a justified larger FPGA.
