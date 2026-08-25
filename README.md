# COSMIC ORGANICS / MORPHOS

**An experimental sparse lattice-computing architecture in which local state transitions perform the computation and can emit independently verifiable causal evidence.**

COSMIC ORGANICS is currently a **research processor stack**, not a production CPU or finished chip. The repository contains a deterministic software model, an integrated sparse-plus-proof kernel, synthesizable 64-processing-element RTL, cryptographic receipt/Merkle/HMAC pipelines, a reproducible application demo, and a frozen FPGA capacity result.

> Core idea: compute only the active causal frontier, commit the resulting transitions, and make the audit trail independently checkable.

## Architecture

```text
localized stimulus / event
          |
          v
+-----------------------------+
| 64-PE A / M / C lattice     |
| local transition law        |
+-----------------------------+
          |
          v
strong dirty-frontier scheduler
          |
          v
authoritative state commit
          |
          +--> deterministic transition receipts
                    |
                    +--> SHA-256 receipt commitments
                              |
                              +--> Merkle-16 roots + inclusion paths
                                           |
                                           +--> HMAC-SHA256 root tags
```

The execution path owns state evolution. Receipt, proof, Merkle, and authentication logic are observers; their values do not decide the next A/M/C state.

## What is supported by the frozen evidence

### Software kernel

COSMIC-KERNEL-05 integrated the strong sparse scheduler with Merkle-bound causal proofs over 288 fresh instances. Dense and sparse systems produced identical states, transition counts, proof representations, and deterministic replay. Proof observation caused zero node-evaluation regression on the frozen workload.

Sparse node-evaluation reduction versus the matching dense system:

| Activity | Reduction |
|---:|---:|
| 1% | **99.1744%** |
| 5% | **96.1569%** |
| 20% | **86.6136%** |
| 100% | **61.3509%** |

Proof payload and hash cost are substantial and are reported separately; they are not hidden inside a synthetic score.

### Synthesizable 64-PE RTL

COSMIC-HW-06 reproduced the same dense/sparse semantics across 256 frozen sequences and 3,072 logical ticks. Sparse RTL reduced enabled PE evaluations by **95.54% at 1% activity**, **86.69% at 5%**, and **54.99% at 20%**, while paying explicit scheduler area/state overhead.

The downstream RTL stack adds, in separate frozen experiments:

- exact 40-bit transition receipts;
- standard SHA-256 receipt commitments;
- SHA-engine throughput controls;
- Merkle-16 roots and four-level inclusion paths;
- two-engine Merkle throughput handoff (`B1_M2`);
- standard HMAC-SHA256 authentication for every frozen Merkle root.

### Application demo

The verified incident-map demo runs a localized 16×16 service-map scenario:

- 256 cells;
- 24 logical ticks;
- 40 completed and audited transitions;
- dense/sparse equality after every tick;
- deterministic replay;
- valid proof acceptance and mutated-claim rejection;
- **97.3307% fewer node evaluations** for the sparse system on this deliberately localized workload.

That percentage describes this demo workload; it is not a universal performance claim.

### Physical FPGA boundary

The complete proof-heavy HW-12 profile was synthesized for the preregistered Lattice ECP5-85F target. Functional, HMAC, harness-preservation, and anti-pruning gates passed, but the exact full stack did **not fit**:

- combinational use: `116,535 / 83,640` (**139%**);
- multipliers: `201 / 156` (**128%**);
- successful routes/bitstreams: `0 / 5` frozen seeds;
- Fmax was therefore not measured.

This is a valid capacity result for that exact device and profile. It does not mean the architecture fails on every FPGA; it means productization now requires a smaller proof profile, more resource sharing, a smaller lattice, off-core proof construction, or a larger target.

## What was falsified or narrowed

The research chain deliberately keeps negative results:

- first-class **Bardo** relations did not beat the strong dirty-node scheduler;
- Bardo-labelled proof compression did not beat an equally expressive generic committed DAG;
- buffering and SHA parallelism are conventional hardware mechanisms, not COSMIC-specific inventions;
- no measured energy, CPU/GPU superiority, quantum, biological-computing, or lattice-QCD-equivalence claim is made.

“Bardo” remains useful as a conceptual name for the committed transition boundary, not as an unsupported uniqueness claim.

## Five-minute reproduction

Requirements: Python 3.11 or 3.12.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e .
make verify
make demo
```

Direct commands:

```bash
python -m unittest -v \
  tests.test_sparse_scheduler \
  tests.test_proof_controls_v02 \
  tests.test_dag_parent_commit \
  tests.test_cosmic_kernel \
  tests.test_verified_incident_map

python -m demos.verified_incident_map --compact
```

Optional RTL HMAC smoke, with Icarus Verilog installed:

```bash
make rtl-smoke
```

The full FPGA place-and-route experiment is intentionally not part of the default fast path; it requires the frozen ECP5 open-source toolchain and is retained as research evidence.

## Processor readiness

The present system is best described as a **specialized verifiable lattice accelerator architecture**.

- software research kernel: demonstrated;
- synthesizable specialized RTL: demonstrated;
- complete cryptographic proof profile: functionally demonstrated in RTL simulation/synthesis;
- fit on the selected mid-range FPGA: not supported for the full profile;
- board execution, measured power, stable host interface, compiler/ISA, and production silicon: not yet demonstrated.

See [Processor readiness](docs/PROCESSOR-READINESS.md) for the milestone and percentage model, and [Research status](docs/RESEARCH-STATUS.md) for the evidence matrix.

## Canonical evidence

- [COSMIC-KERNEL-05 — integrated sparse + committed proof](https://github.com/safal207/COSMIC-ORGANICS/pull/69)
- [COSMIC-HW-06 — 64-PE dense vs sparse RTL](https://github.com/safal207/COSMIC-ORGANICS/pull/72)
- [COSMIC-HW-12 — HMAC-authenticated Merkle-root cost](https://github.com/safal207/COSMIC-ORGANICS/pull/94)
- [COSMIC-HW-13 — ECP5 physical capacity boundary](https://github.com/safal207/COSMIC-ORGANICS/pull/97)
- [Verified incident-map application demo](https://github.com/safal207/COSMIC-ORGANICS/pull/99)
- [COSMIC-RELEASE-01 milestone](https://github.com/safal207/COSMIC-ORGANICS/issues/98)

Historical preregistrations, negative results, manifests, tests, and machine-readable evidence remain in the repository and frozen branches.

## License

Apache-2.0.
