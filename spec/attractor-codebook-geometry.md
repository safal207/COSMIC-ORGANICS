# MORPHOS-S3 — Attractor Codebook Geometry

## Status

HYPOTHESIS / diagnostic computational experiment.

## Question

Does one-bit recovery fail partly because sampled stable binary attractors are too close to be uniquely identifiable after perturbation?

S3 does **not** change MORPHOS dynamics and does not tune any parameter. It analyzes the frozen MajorityCA, MORPHOS-S1, and MORPHOS-S2 dynamics on fresh deterministic corpora.

## Codebook view

For a model/corpus, let the sampled binary fixed attractors be

`C = {a_1, ..., a_n}`.

Define Hamming distance

`d(a_i, a_j) = number of cells that differ`.

The sampled minimum code distance is

`d_min = min_{i != j} d(a_i, a_j)`.

For a binary codebook, `d_min >= 3` is sufficient for unique nearest-codeword identification after any single-bit corruption. S3 uses this only as a coding-theory diagnostic analogy; the sampled MORPHOS attractors are not claimed to be a quantum code or an exhaustive error-correcting code.

## Strong collision case

If two fixed attractors differ by one bit, then flipping that bit in one attractor produces the other attractor exactly.

For deterministic state-only dynamics this is a hard ambiguity: the corrupted state is already another valid fixed state. Without additional context, history, parity, mirror state, or another independent coordinate, the original target cannot be inferred from the current state alone.

S3 records these direct codeword-collision trials separately from weaker nearest-codeword ambiguity.

## Frozen protocol

- No parameter discovery.
- Frozen S1 exponent: `0.25`.
- Frozen S2 hierarchy exponent: `0.06`.
- Frozen S2 domain size: `3`.
- Fresh SHA-256-derived corpora dated `20260825xx`.
- Same initial corpus is evaluated by MajorityCA, S1, and S2.
- One-bit perturbation trials are deterministically capped per model/corpus.

For each sampled codebook S3 records:

- codebook size and sampled capacity proxy;
- minimum Hamming distance;
- mean nearest-attractor distance;
- number of distance-1 and distance-2 attractor pairs;
- whether `d_min >= 3` gives a sampled one-bit unique-decoding guarantee;
- fraction of one-bit trials where the original attractor is the unique nearest codeword;
- nearest-codeword ambiguity fraction;
- direct codeword-collision fraction;
- actual dynamic recovery overall and by geometry bucket;
- share of observed recovery failures forced by direct fixed-codeword collisions.

## Interpretation boundary

A sampled distance or collision result is evidence about the declared finite codebook only. It is not exhaustive channel capacity, not a proof about all attractors, not a calibrated physical energy landscape, and not quantum error correction.

The purpose is causal diagnosis: distinguish failures that are already implied by state-space geometry from failures that remain attributable to the transition dynamics/decoder.

## Next causal branch

If geometry creates hard ambiguity, the next architecture should add an independent coordinate rather than merely increasing repair pressure. Candidate: **MORPHOS-M1 Reflective State Dynamics**, where a state carries or induces a complementary/mirror observation that can disambiguate otherwise colliding basins.
