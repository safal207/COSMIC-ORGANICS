# COSMIC Product Profiles

The HW-13 result shows that the full proof-complete stack should not be treated as one mandatory hardware configuration. Productization needs explicit profiles with different trust, cost, and latency boundaries.

These are **proposed product profiles** assembled from measured building blocks. Only the underlying components have frozen evidence; the complete CORE and AUDIT physical profiles still require their own workload-bound validation.

## 1. CORE — sparse transition engine

```text
stimulus -> A/M/C lattice -> dirty frontier -> committed next state
```

### Includes

- local A/M/C state;
- strong dirty-frontier scheduling;
- deterministic synchronous transition semantics;
- basic transition counters and health telemetry.

### Excludes

- full receipt export;
- SHA commitments;
- Merkle trees and inclusion paths;
- HMAC authentication.

### Best fit

- event-driven simulation;
- localized control and monitoring;
- embedded workloads where an external system already owns audit logging;
- first physical fit/power experiment.

### Evidence

HW-06 supports exact dense/sparse RTL semantics and strong low-activity PE-evaluation reduction. A compact CORE-only physical profile has **not** yet been placed and routed.

## 2. AUDIT — practical near-term profile

```text
CORE
  -> ordered transition receipts
  -> SHA-256 batch commitments
  -> optional incident-triggered or sampled causal proof
  -> external storage / verifier
```

### Includes

- CORE;
- deterministic transition receipts;
- SHA-256 batch commitment, preferably with the measured x2 throughput point;
- configurable proof policy;
- external persistence and verification API.

### Recommended proof policies

1. **Incident-triggered:** prove all transitions inside a flagged causal window.
2. **Sampled:** prove a deterministic percentage of routine transitions.
3. **Escalation:** retain commitments continuously and construct richer proof off-core when a dispute occurs.
4. **Full local window:** disclose a bounded region around a decision rather than the entire system history.

### Why this is the strongest product candidate

- It preserves independently checkable evidence without forcing every Merkle/proof/HMAC component onto a mid-range FPGA.
- The software kernel already supports proof sampling and exact mutation rejection.
- SHA256x2 passed the frozen throughput gate.
- It maps naturally to AI-agent audit, industrial incident reconstruction, payment/settlement verification, and regulated automation.

### Unresolved

- exact on-core/off-core split;
- receipt memory organization;
- persistent storage format;
- buyer-specific latency and retention policy;
- public signature or external anchor.

## 3. FULL-PROOF — maximum local evidence profile

```text
AUDIT
  -> Merkle-16 roots
  -> inclusion path for every real leaf
  -> HMAC-SHA256 authenticated roots
```

### Includes

- 100% transition receipt commitment;
- every-leaf Merkle inclusion proof;
- authenticated root metadata.

### Evidence

The complete chain is functionally verified in software/RTL. HW-12 produced exact roots, proofs, and HMAC tags. HW-13 showed that the frozen implementation does **not** fit the ECP5-85F target.

### Admitted deployment options

- larger FPGA selected before measurement;
- smaller lattice;
- shared/serialized crypto engines;
- BRAM-backed receipt and tree storage;
- proof construction moved partly or fully off-core;
- custom ASIC only after a real workload justifies the cost.

### Not a default product

FULL-PROOF is an audit appliance or accelerator profile, not the minimum viable processor. Treating it as mandatory would force every customer to pay for evidence they may not need.

## Decision rule for the next pilot

Choose the profile from the buyer's threat model:

| Buyer question | Recommended profile |
|---|---|
| “Can the system react efficiently to localized events?” | CORE |
| “Can I later prove what happened and detect tampering?” | AUDIT |
| “Must every transition carry a locally generated inclusion proof?” | FULL-PROOF |
| “Do third parties need non-repudiation?” | AUDIT or FULL-PROOF plus a future public-signature/anchoring layer |

The default commercial hypothesis is **AUDIT**, because it keeps the strongest verified differentiator—causal evidence—without inheriting the entire HW-13 capacity cost.
