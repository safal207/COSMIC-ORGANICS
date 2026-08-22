# BARDO-EDGE-01 — Edge-Native Transition Representation

Status: **PREREGISTERED BEFORE CANDIDATE RESULTS**

Tracking issue: #56

Exact parent head:

```text
55ee39d9c248cb3b6f4f93359740e502ae9ad41e
```

This experiment is stacked on the existing MORPHOS A/M/C + W8.5 benchmark surface. It does not modify W8.5 dynamics.

## Question

Does making transitions first-class edge objects improve transition observability, audit/replay work, or representation economics relative to node-only MORPHOS state — and does any benefit remain after comparison with an equally expressive conventional explicit-edge control?

## Frozen systems

### A — NODE_ONLY

Current frozen MORPHOS/W8.5 behavior. No transition-edge object is available to the consumer. Transition history is reconstructed from the ordinary per-tick A/M/C state trace.

### B — CONVENTIONAL_EDGE

A competent explicit transition-event representation. For every observed local phase change it records the same semantic information available to the Bardo candidate:

```text
site
from_phase
to_phase
logical_tick
source_site | null
destination_site | null
admissible
evidence_ref | null
```

The control may use an indexed in-memory representation. It is not forced to scan JSON or use deliberately inefficient plumbing.

### C — BARDO_EDGE

The same transition facts are represented as an edge-native field object whose identity is the transition relation rather than only the destination node state.

```text
B_ij(t) = relation(source, destination, transition, evidence, logical_time)
```

BARDO_EDGE receives no future target truth, no extra witness, no stronger authority, and no hidden state unavailable to CONVENTIONAL_EDGE.

## Authority boundary

BARDO-EDGE-01 v0.1 is **observational only**.

Neither explicit-edge system may alter:

```text
state updates
repair ownership
protected_targets
witness drive
transition threshold
coupling
parity code
commit delay
evaluation horizon
retention horizon
```

Therefore any recovery difference versus NODE_ONLY is a bug and fails the experiment.

## Fresh held-out corpus

Two complete seed families are frozen before the first candidate result.

```text
5x5: 202608179001 202608179002 202608179003
7x7: 202608179011 202608179012 202608179013
9x9: 202608179021 202608179022 202608179023

5x5: 202608180001 202608180002 202608180003
7x7: 202608180011 202608180012 202608180013
9x9: 202608180021 202608180022 202608180023
```

Use 48 frozen single-bit common-mode trials per corpus, matching the existing W8.x workload shape.

Total fresh trials:

```text
18 corpora * 48 = 864 trials
```

These seeds must not be used for post-result tuning.

## Required transition correctness

For B and C:

1. every actual A/M/C phase change emits exactly one corresponding transition record;
2. no record may claim a phase change that did not occur;
3. replaying the ordered transition records from the same initial state reproduces the exact observed final state;
4. record order uses logical simulator time, not wall-clock time;
5. identical execution produces byte-stable canonical transition identities;
6. evidence fields are descriptive unless an existing MORPHOS witness already establishes them — the logger may not invent authority.

## Measurements

### Utility

```text
exact recovery @ tick 8
exact recovery @ tick 12
previous-success regressions
phase-change coverage
phantom transition count
ambiguous transition reconstructions
```

### Proof / auditability

```text
transition records required to reconstruct a selected trajectory
state observations required for NODE_ONLY reconstruction
replay equality
transition identity stability
source/destination relation coverage
```

### Cost

```text
transition metadata bytes
peak transition representation objects
edge writes
edge reads during replay
additional allocations where measurable
```

### Speed

```text
runtime / trial
transition replay time
trajectory reconstruction time
```

No synthetic winner score is allowed.

## Frozen acceptance logic

### Representation usefulness

Explicit transition representation is supported only if at least one of B or C:

- reduces median trajectory-reconstruction work by >= 25% versus A, or
- removes a reconstruction ambiguity present in A,

while preserving exact simulator outcomes and producing zero phantom transitions.

### Bardo-specific value

BARDO_EDGE earns a distinct claim only if C beats B on at least one preregistered cost/speed/audit metric by >= 10% while:

```text
transition semantic coverage(C) == transition semantic coverage(B)
replay correctness(C) == replay correctness(B) == 100%
phantom transitions(C) == 0
outcome behavior(C) == outcome behavior(B) == NODE_ONLY
```

A tie means the value belongs to explicit-edge architecture generally, not uniquely to Bardo.

### Fail closed

The experiment is rejected if either explicit-edge implementation:

- changes MORPHOS recovery behavior;
- uses target truth or future phase information;
- drops a real phase change;
- emits a phantom transition;
- cannot deterministically replay its own transition history;
- changes the frozen workload, thresholds, seeds, or W8.5 mechanism after results are observed.

## Interpretation table

```text
A ~= B ~= C
  -> edge representation adds no measured value here

B and C > A, B ~= C
  -> explicit transition representation is useful; no Bardo-specific advantage

C > B > A
  -> candidate Bardo representation earns a narrow implementation/economics claim

C improves one metric but loses semantic coverage or replay correctness
  -> reject Bardo-specific promotion
```

## Claim boundary

Classical deterministic software/lattice evidence only.

No claim of quantum behavior, physical spacetime discretization, lattice-QCD equivalence, biological life, consciousness, silicon performance, physical energy advantage, novelty/patentability, or universal processor superiority follows from a PASS.

## Next step after preregistration

Implement the two controls first, freeze their executable contract, then add BARDO_EDGE without changing the corpus or acceptance logic.