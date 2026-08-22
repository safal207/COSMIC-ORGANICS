# BARDO-PROOF-03 — Proof-Carrying Transition Experiment

Status: **PREREGISTERED BEFORE BARDO CANDIDATE IMPLEMENTATION**

Tracking issue: #62

Parent head:

`2021c7ea03519f58c30e37c6e720b6a1db4e4d32`

## Motivation

BARDO-FRONTIER-02 showed that a first-class relation frontier did not reduce node evaluations beyond a strong conventional dirty-node scheduler. Therefore BARDO-PROOF-03 does not test scheduler speed. It asks whether transition relations can earn value as proof/audit objects.

Timing cannot decide this experiment.

## Question

Can a proof-carrying transition relation verify a selected causal transition chain with less deterministic proof payload or verification work than strong conventional proof representations?

## Frozen systems

### SNAPSHOT_LOCAL

For every queried transition, disclose the complete pre-tick lattice snapshot plus the queried site's local stimulus and claim. The verifier recomputes only the queried site. This is a strong compute baseline but intentionally exposes the data cost of carrying global snapshots.

### LOCAL_WITNESS

For every queried transition, disclose only the facts needed by the frozen local transition law:

- logical tick;
- site;
- phase before;
- neighbor site/phase pairs;
- local stimulus;
- claimed phase after.

This is the minimal conventional local-witness anti-strawman. Repeated facts across queried transitions are not intentionally padded, but each witness remains independently verifiable.

### CAUSAL_DAG

Strong conventional proof control. It canonicalizes/deduplicates phase and stimulus facts across the whole queried chain and records parent transition identities for causal composition. It may share repeated facts and references efficiently.

This control exists so BARDO cannot win merely because it stores a graph while the baseline stores disconnected JSON objects.

### BARDO_PROOF_EDGE

Candidate, absent at preregistration freeze. The transition relation itself is the canonical proof object and may compose parent relation identities with shared boundary facts.

It receives no facts unavailable to CAUSAL_DAG.

## Frozen local law

Verification uses the existing MORPHOS `Grid2D` A/M/C local transition semantics. A verifier may use only the disclosed pre-tick local facts plus the frozen configuration. It may not inspect the live model, target state, undisclosed snapshot cells, or future state.

## Workload

Fresh deterministic query families:

- grids: 16x16, 32x32, 64x64;
- chain lengths: 1, 4, 16, 64;
- seeds: 202608226201 and 202608226202;
- 8 trials per grid × chain length × seed family;
- total: 192 proof queries;
- sparse activity density: 5%;
- pulse magnitude: 0.9;
- maximum source trace: 96 logical ticks.

Queries must include deterministic overlapping/branching local transitions when available. A corpus that cannot supply the frozen requested chain length is a workload failure; the candidate may not silently shorten it.

## Frozen mutations

Every proof system must be tested against the same six mutation families where the representation contains the corresponding semantic field:

1. wrong claimed next phase;
2. mutated local stimulus;
3. mutated neighbor phase;
4. wrong logical tick;
5. missing required parent;
6. substituted parent identity.

For representations without explicit parent fields, parent mutations are marked non-applicable rather than counted as false failures. The required invalid-proof detection rate is computed over all applicable frozen mutations.

## Primary metrics

Decision-bearing evidence is deterministic:

- canonical proof payload bytes;
- unique phase facts disclosed;
- unique stimulus facts disclosed;
- parent references disclosed;
- local transition evaluations;
- hash evaluations;
- proof objects traversed;
- invalid-proof detection rate.

Wall-clock verification time is diagnostic only.

No synthetic winner score is allowed.

## Acceptance logic

### Local proof value

LOCAL_WITNESS supports proof-locality value only if it reduces canonical proof payload by at least 25% versus SNAPSHOT_LOCAL while preserving 100% valid-proof acceptance and 100% applicable invalid-proof rejection.

### Causal DAG value

CAUSAL_DAG earns a distinct generic causal-graph result if it improves at least one preregistered proof payload/work metric by at least 10% versus LOCAL_WITNESS on multi-transition chains, with no soundness regression.

### Bardo-specific value

BARDO_PROOF_EDGE earns a distinct claim only if it improves at least one preregistered primary proof-size/work metric by at least 10% versus CAUSAL_DAG while:

- valid-proof acceptance = 100%;
- applicable invalid-proof rejection = 100%;
- transition-law agreement = 100%;
- no other primary proof-size/work metric regresses by more than 2% unless that tradeoff was frozen before candidate implementation.

A timing-only win cannot count.

A tie with CAUSAL_DAG is `CAUSAL_DAG_VALUE_ONLY`, not a Bardo-specific success.

## Allowed decisions

- `CONTROL_FAILURE`
- `INCOMPLETE_REQUIRED_METRICS`
- `NO_PROOF_LOCALITY_VALUE`
- `LOCAL_PROOF_VALUE_ONLY`
- `CAUSAL_DAG_VALUE_ONLY`
- `BARDO_PROOF_VALUE_SUPPORTED`

## Claim boundary

Classical deterministic software proof/audit experiment. Hashes here provide canonical identity/integrity checks for the tested representation; this experiment does not establish a general cryptographic-security theorem, quantum property, physical-energy result, or hardware advantage.
