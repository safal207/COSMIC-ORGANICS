# COSMIC-KERNEL-05 — preregistration

Status: **frozen before integrated kernel implementation**.

Parent research head: `7c047673c8b4d5d49e19e699558560db9b099ded`.

## Why this experiment exists

The previous adversarial sequence separated useful mechanisms from naming effects:

- sparse dirty-node execution replicated large node-evaluation savings under sparse activity;
- first-class Bardo relations did not improve scheduling beyond that strong control;
- Merkle-bound local transition proofs rejected substituted state facts without hidden runtime access;
- parent-set commitment compacted causal ancestry;
- a generic committed DAG matched frozen Bardo exactly, so that compression is not Bardo-specific.

COSMIC-KERNEL-05 stops asking whether a representation name is special. It asks whether the surviving mechanisms compose into a useful integrated lattice kernel.

## Frozen systems

1. `DENSE_EXECUTION`: full synchronous node sweep; no proof generation.
2. `DENSE_COMMITTED_PROOF`: the same dense execution plus generic Merkle-bound, parent-set committed causal proofs.
3. `SPARSE_EXECUTION`: strong deduplicated dirty-node scheduler; no proof generation.
4. `SPARSE_COMMITTED_PROOF`: the same sparse execution plus the same generic proof mechanism.

The integrated candidate file `morphos/cosmic_kernel.py` must be absent on the frozen control head.

## Fresh workload

- grids: 16x16, 32x32, 64x64;
- activity: 1%, 5%, 20%, 100%;
- proof sampling: 1%, 10%, 100% of completed transitions by deterministic SHA-256 sampling;
- fresh seed families: `202608236701`, `202608236702`;
- four trials per grid × activity × proof-density × seed-family;
- 288 total instances;
- 24 logical ticks, injections at ticks 1, 9, 17;
- pulse magnitude 0.9;
- zero memory decay.

## Correctness and proof gates

Comparable systems must preserve state equality at every logical tick and identical transition counts. Deterministic replay must hold. Proof-enabled systems require 100% valid-proof acceptance and 100% frozen invalid-proof rejection.

No target truth or future state may enter execution or verification.

## Metrics stay separate

Execution counts and proof counts are not interchangeable units. We report node evaluations, scheduled work, writes, and avoided evaluations separately from proof bytes, Merkle hashes, hash evaluations, parent commitments, and proof objects.

No synthetic combined primary score is allowed. Wall-clock runtime is diagnostic only.

## Main falsifiable test

On fresh 1% and 5% activity bands, `SPARSE_COMMITTED_PROOF` must retain at least 50% fewer node evaluations than `DENSE_COMMITTED_PROOF` while passing every semantic and proof gate.

The 100% activity condition is a required negative control and must be reported even if sparse bookkeeping loses.

Possible outcomes:

- `CONTROL_FAILURE`
- `SPARSE_VALUE_NOT_REPLICATED`
- `SPARSE_VALUE_PROOF_OVERHEAD_TOO_HIGH`
- `SPARSE_PLUS_PROOF_PARETO_SUPPORTED`

## Claim boundary

This is a classical deterministic software-kernel experiment. It does not establish custom-silicon, physical-energy, quantum, CPU/GPU/TPU, or Bardo-specific superiority.
