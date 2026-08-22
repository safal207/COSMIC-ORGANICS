# BARDO-FRONTIER-02 — Preregistered Sparse Scheduling Experiment

Status: **PREREGISTERED BEFORE BARDO CANDIDATE IMPLEMENTATION**

Tracking issue: #59

Parent head:

`565570e2c6c1942ad1f5c755fca654421f61b609`

## Why this experiment exists

BARDO-EDGE-01 mechanically emitted a Bardo-specific PASS, but the discriminating timing path was later found to execute the same reconstruction code for both edge systems. That result is retained historically but is not accepted as causal evidence for a Bardo-specific advantage.

BARDO-FRONTIER-02 removes that ambiguity. A distinct Bardo claim can only come from **architecture-specific operation counts**. Wall-clock timing is secondary and cannot decide the claim.

## Question

When lattice activity is sparse, can a relation-native frontier reduce the number of actual node evaluations required for exact deterministic MORPHOS evolution beyond both:

1. a full dense node sweep, and
2. a competent conventional dirty-node scheduler?

## Frozen model surface

This experiment uses the existing `morphos.grid2d.Grid2D` local A/M/C transition law with the following fixed configuration:

- memory decay: 0.0
- anchor threshold: 0.5
- adaptive threshold: 0.35
- anchor coupling: 0.75
- adaptive coupling: 0.5
- mixed relax threshold: 0.05
- checkerboard mask
- von Neumann neighborhood

The W8.x witness/recovery stack is not part of this scheduling experiment. BARDO-FRONTIER-02 isolates scheduler semantics so exact equivalence can be tested without mixing in recovery authority.

## Systems

### DENSE_NODE

Reference synchronous execution. Every node is evaluated on every logical tick.

### DIRTY_NODE

Strong conventional sparse control. It evaluates only nodes whose local inputs may have changed:

- sites whose external stimulus changed since the previous tick;
- sites that changed phase on the previous tick;
- neighbors of sites that changed phase on the previous tick.

The scheduled set is deduplicated and evaluated in deterministic site order. Updates remain synchronous: all scheduled evaluations at tick `t` read the same pre-tick state and commit together.

### BARDO_FRONTIER

Candidate system. It must derive work from first-class transition/influence relations rather than a dirty-node set. It receives no future state truth and no stronger transition law.

The BARDO candidate is intentionally absent at preregistration freeze.

## Exactness gates

For every trial and every logical tick:

- state string must equal DENSE_NODE exactly;
- cumulative transition count must equal DENSE_NODE exactly;
- logical tick must match;
- all systems receive identical stimulus vectors;
- deterministic ordering is required;
- no system may use future state truth.

Any mismatch is `CONTROL_FAILURE`.

## Frozen workload

Three grid sizes:

- 16x16
- 32x32
- 64x64

Four externally stimulated activity densities:

- 1%
- 5%
- 20%
- 100%

Two fresh deterministic seed families:

- 202608225901
- 202608225902

Eight trials per grid × density × seed family.

Total: **192 trials**.

Each trial runs for 24 logical ticks with one-tick signed stimulus injections at ticks 1, 9, and 17. Pulse magnitude is 0.9. Initial A/C states are deterministically generated and relaxed with DENSE_NODE to a fixed point before measurement; fixed-point preconditioning is capped at 64 ticks and failure to reach a fixed point invalidates the trial.

The 100% density band is a required negative control. Sparse bookkeeping is allowed to lose there; no universal speed claim may be made from sparse-only results.

## Primary metrics

Decision-bearing metrics use counts, not timing:

- node evaluations;
- scheduled work items;
- unchanged node evaluations avoided;
- state writes;
- transition records emitted.

Diagnostic metrics:

- relation evaluations;
- frontier insertion attempts;
- dedup hits;
- wall-clock runtime.

No synthetic combined winner score is allowed.

## Frozen decision logic

### Generic sparse execution value

`DIRTY_NODE` supports generic sparse-execution value only if it reduces node evaluations by at least 25% versus DENSE_NODE in the sparse activity bands while preserving exact semantics.

### Bardo-specific value

`BARDO_FRONTIER` supports a distinct Bardo claim only if:

1. all exactness gates pass;
2. it performs at least 10% fewer **node evaluations** than DIRTY_NODE in at least two of the three sparse density bands (1%, 5%, 20%);
3. it never performs more node evaluations than DIRTY_NODE in any sparse density band;
4. timing is not the deciding route.

If BARDO_FRONTIER ties DIRTY_NODE, the result is `SPARSE_EXECUTION_VALUE_ONLY`.

## Allowed decisions

- `CONTROL_FAILURE`
- `INCOMPLETE_REQUIRED_METRICS`
- `NO_SPARSE_EXECUTION_VALUE`
- `SPARSE_EXECUTION_VALUE_ONLY`
- `BARDO_FRONTIER_VALUE_SUPPORTED`

## Claim boundary

This is a classical deterministic software scheduling experiment. It is not a quantum-computing result, a physical-energy measurement, or a custom-silicon benchmark.
