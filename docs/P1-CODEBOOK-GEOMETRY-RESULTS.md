# P1 — MORPHOS-S3 Attractor Codebook Geometry Results

## Question

Does the large-scale one-bit recovery failure of MORPHOS-S2 come from attractors being too close to distinguish after perturbation?

## Protocol

S3 changes no dynamics and tunes no parameter. It freezes S1 (`alpha=0.25`) and S2 (`beta=0.06`, domain size `3`) and analyzes nine fresh SHA-256-derived corpora: three each at 5×5, 7×7, and 9×9.

Each sampled set of binary fixed attractors is treated as a finite diagnostic codebook. We measure Hamming distance, one-bit nearest-codeword identifiability, direct codeword collisions, and actual dynamic recovery.

## Main result

The attractive hypothesis was **not** the main explanation for the scale failure.

Across all six larger-grid S2 corpora (7×7 and 9×9):

- sampled minimum distance is always at least `8`;
- all `6/6` corpora satisfy the sampled `d_min >= 3` one-bit unique-decoding condition;
- one-bit `unique_nearest_fraction = 1.0` on all six;
- direct one-bit codeword collisions = `0` on all six;
- yet mean dynamic recovery is only `0.336041667`.

So the sampled codebook geometry says the original attractor is uniquely identifiable under the declared Hamming diagnostic, while the actual S2 transition dynamics recover only about `33.6%` of trials.

The gap between unique identification and dynamic recovery is:

```text
1.000000000 - 0.336041667 = 0.663958333
```

That is direct evidence that **large-scale recovery collapse is primarily not explained by nearest-codeword ambiguity in the sampled codebook**.

## Baseline context

Mean dynamic recovery on the same six larger-grid corpora:

```text
MajorityCA  0.710625000
MORPHOS-S1 0.293333333
MORPHOS-S2 0.336041667
```

S2 improves over S1, as the previous hierarchical experiment showed, but remains far below MajorityCA despite having very well-separated sampled attractors.

## Local 5×5 collision evidence

Geometry still matters locally.

Two of the three 5×5 S2 corpora contain distance-1 attractor pairs. Their direct collision trials never recover to the original attractor, exactly as expected for deterministic state-only dynamics when the corrupted state is already another fixed attractor.

However, these hard collisions explain only a small part of 5×5 recovery failures:

```text
mean hard-collision share of failures = 0.005604615
```

So even where hard ambiguity exists, it is not the dominant error source in this sample.

## Falsification result

The hypothesis

> "large-scale recovery is bad because stable states are too close"

is **not supported** by the frozen S3 evidence.

The evidence instead points upward in the causal stack:

```text
codebook geometry: sufficiently separated on 7×7 / 9×9
          ↓
identity after one-bit corruption: uniquely recoverable in Hamming space
          ↓
actual MORPHOS transition dynamics: still fail often
          ↓
next refactor target = decoder / basin flow / transition policy
```

## What this means for reflective dynamics

MORPHOS-M1 remains interesting, but its justification changes.

A mirror/reflective coordinate is **not required to solve the observed large-scale nearest-codeword ambiguity**, because S3 finds none on the declared larger-grid sample.

M1 should instead be tested as a different mechanism:

- independent self-observation;
- transition verification;
- basin-direction disambiguation during motion, not only at the endpoint;
- memory of intended/previous state;
- detection of a transition that is moving away from the target basin.

This is a stronger and more falsifiable role than "add a mirror because attractors collide".

## Scientific boundary

This is finite sampled binary fixed-attractor geometry. It is not exhaustive channel capacity, not a proof over all attractors, not a physical energy landscape, and not a quantum error-correcting code.

## Portable evidence

```text
schema: cosmic-organics/codebook-summary-0.2
digest: 735a233f3f2b35ac47ab5afcbf23cd5642b757e616f7b470d884599b2eb1698d
```
