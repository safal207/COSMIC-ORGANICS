# COSMIC-HW-06 frozen PE interface

This interface is a preregistered hardware contract, not an RTL implementation.

## Processing element state

Each of 64 PEs stores only the architectural state required by the first hardware boundary:

- `phase[1:0]`: A=00, M=01, C=10; 11 is invalid/reserved;
- local stimulus input for the current logical tick;
- four neighbor phase inputs (N/S/E/W, boundary-valid mask);
- anchor/adaptive role bit derived from the frozen mask;
- transition-valid / state-write indication.

No target answer, future state, proof verdict, or external outcome may feed the transition decision.

## Logical tick contract

1. Capture the current phase vector and current stimulus vector.
2. Determine the active PE set according to the selected scheduler (dense or sparse).
3. Evaluate all active PEs from the same pre-tick phase snapshot.
4. Commit resulting phase changes synchronously.
5. Update dirty/frontier bookkeeping from committed changes.
6. Only after commit, optional proof/receipt logic may observe the transition event.

Sparse scheduling must not introduce asynchronous semantic ordering between PEs.

## First RTL scope

The first candidate may use a centralized 64-bit active mask/frontier rather than a distributed NoC. This keeps the initial experiment focused on semantic equivalence and scheduler economics. Distributed routing, Morphos topology mutation, ATMAN observer feedback, and physical Merkle/SHA hardware are later experiments.

## Receipt boundary

The initial proof-capable RTL may emit a compact transition receipt record containing logical tick, PE/site id, previous phase, next phase, and an externally computed/attached commitment reference. A physical SHA/Merkle accelerator is not required for HW-06/v0.1 and must not be counted as present unless actually instantiated and synthesized.
