# COSMIC ORGANICS — research status

This document separates **supported evidence** from names, metaphors, and future product claims.

“Validated” in this repository means that a frozen experiment has reproducible software tests, RTL simulation, synthesis, or physical-flow evidence under its stated boundary. It does **not** mean peer-reviewed physics, security certification, production silicon, or commercial readiness.

## Evidence matrix

| Boundary | Frozen evidence | Decision | What it supports | What it does not support |
|---|---|---|---|---|
| BARDO-FRONTIER-02 | strong dirty-node control versus first-class relation frontier | `SPARSE_EXECUTION_VALUE_ONLY` | sparse active-frontier execution is valuable | Bardo relations are not uniquely faster than a strong conventional scheduler |
| BARDO-PROOF-04 | generic committed DAG versus Bardo-labelled proof edge | `GENERIC_PARENT_COMMITMENT_VALUE_ONLY` | committed parent sets can reduce causal-proof repetition | Bardo-labelled representation has no measured unique compression advantage |
| COSMIC-KERNEL-05 | 288 fresh integrated sparse+proof instances | `SPARSE_PLUS_PROOF_PARETO_SUPPORTED` | exact sparse/dense semantics, deterministic replay, committed causal proofs, no proof-driven execution authority | universal workload speedup, physical energy, CPU/GPU superiority |
| COSMIC-HW-06 | 64-PE dense and sparse RTL, 256 sequences, 3,072 ticks | `SPARSE_RTL_VALUE_SUPPORTED` | synthesizable local-state lattice and sparse scheduler with exact dense equivalence | board power, placed/routed timing, production FPGA fit |
| COSMIC-HW-07…09 | finite receipts and standard SHA-256 commitment pipeline | measured receipt/SHA cost and throughput frontier | deterministic transition export and exact SHA commitments | signatures, non-repudiation, secure key storage |
| COSMIC-HW-10…11 | Merkle-16 roots, four-level inclusion proofs, B1_M2 handoff | `MERKLE_INCLUSION_COST_MEASURED`; `MERKLE_THROUGHPUT_VALUE_SUPPORTED` | every real leaf can receive an independently verifiable inclusion path | free proof generation or COSMIC-specific uniqueness of generic hash parallelism |
| COSMIC-HW-12 | HMAC-SHA256 over all 444 frozen Merkle roots | `HMAC_ROOT_AUTH_COST_MEASURED` | exact keyed authentication of scoped root records with measured RTL cost | public signatures, non-repudiation, production key management, side-channel resistance |
| COSMIC-HW-13 | exact full HW-12 profile targeted to ECP5-85F over five frozen seeds | `DEVICE_CAPACITY_NOT_SUPPORTED` | honest physical capacity boundary for one exact device/profile | failure on every FPGA or evidence that a smaller profile cannot fit |
| Verified incident map | 16×16 localized service map, 24 ticks | demo PASS | deterministic application mapping, sparse/dense equality, replay, proof acceptance/rejection | a universal 97% speed or energy claim |

## Canonical result heads

| Experiment | Source head | Primary record |
|---|---|---|
| COSMIC-KERNEL-05 | `8e7e040eb305619c459e0caf66225a4c6a1e3f9c` | PR #69 |
| COSMIC-HW-06 | `5b3b4c8c77ffdbe17ad573951cca59a1c15aeb44` | PR #72 |
| COSMIC-HW-12 | `7bad7ba095c65221e057696df40fcd6c53dee2b8` | PR #94 |
| COSMIC-HW-13 | `773b68597b9136c12867ecc1a3a1749edcba1627` | PR #97 |
| Verified incident map | `39aa1f9b4d16bf33f7ce48be34000cad7ae3494b` | PR #99 |

## Supported numerical claims

### Integrated software kernel

Across the frozen COSMIC-KERNEL-05 corpus, sparse node-evaluation reductions versus the matching dense system were:

- 1% activity: **99.1744%**;
- 5% activity: **96.1569%**;
- 20% activity: **86.6136%**;
- 100% activity: **61.3509%**.

All frozen state, transition-count, proof-representation, and deterministic-replay mismatches were zero. Proof observation caused zero additional node evaluations. Proof payload and hash work remain separate costs.

### 64-PE RTL

COSMIC-HW-06 sparse enabled-PE reductions versus dense RTL were:

- 1% activity: **95.54%**;
- 5% activity: **86.69%**;
- 20% activity: **54.99%**;
- 100% activity: **16.67%**.

The sparse scheduler paid explicit structural overhead: LUT `5,550 → 6,118`, FF `193 → 832`, mapped core cells `9,706 → 10,930`, and depth proxy `13 → 19` in the frozen Xilinx-7 structural mapping.

### Authenticated proof profile

COSMIC-HW-12 preserved the complete frozen receipt/leaf/root/proof stream while authenticating `444 / 444` Merkle roots. Relative to B1_M2 control:

- physical simulation cycles: `624,253 → 695,692` (**+11.44%**);
- LUT: `48,437 → 58,558` (**+20.90%**);
- FF: `24,287 → 28,780` (**+18.50%**);
- core cells excluding I/O: `75,967 → 92,632` (**+21.94%**);
- logic-depth proxy remained `266`;
- root-to-HMAC stalls remained zero on the frozen workload.

### Physical capacity boundary

On the frozen ECP5-85F target, the exact full proof-heavy profile exceeded available resources before routing:

- combinational use: `116,535 / 83,640` (**139%**);
- multipliers: `201 / 156` (**128%**);
- successful routed and packed seeds: `0 / 5`;
- post-route Fmax: unmeasured because capacity failed first.

Reaching nominal capacity therefore requires at least about **28.2% less combinational use** and **22.4% fewer multiplier instances**, before any routing/timing margin is considered. This is a derived lower bound, not a guarantee of successful routing.

## Claim boundary

The repository currently supports the description:

> An experimental, synthesizable sparse lattice-computing architecture with deterministic transition receipts and independently checkable causal-proof machinery.

It does not currently support claims of:

- a finished general-purpose CPU;
- a production FPGA bitstream;
- measured watts or joules per transition;
- placed/routed Fmax for the full profile;
- CPU/GPU superiority;
- quantum or biological computation;
- equivalence to lattice QCD;
- production cryptographic key security;
- security certification;
- ASIC PPA or production silicon readiness.

## Research discipline

The project retains negative and narrowing results because they improve the architecture:

1. names do not receive credit when strong conventional controls tie them;
2. result, proof, cost, and speed remain separate dimensions;
3. thresholds, seeds, targets, and handoff rules are frozen before candidate interpretation;
4. harness and CI failures are separated from scientific negative results;
5. a device-capacity failure is reported as capacity, not disguised as timing or semantic failure.
