# P1 — MORPHOS-M1 Reflective Recovery Results

## Question

Can a MORPHOS lattice use an internal delayed self-image to detect and correct local divergence without receiving the correct target state from an external oracle?

## Mechanism

M1 is stacked on the frozen S2 dynamics.

Each cell has:

```text
primary phase S_i
mirror phase  R_i
stability counter
```

The mirror contributes:

```text
mirror_drive = 0.15 * (q(mirror) - q(primary))
```

and only recommits after the primary has remained unchanged for three ticks.

The mirror is therefore persistent redundancy, not an externally supplied answer.

## Confirmation protocol

Nine fresh SHA-256 corpora are frozen:

- three `5×5`;
- three `7×7`;
- three `9×9`.

Each corpus builds binary fixed targets using frozen S2 dynamics. Up to 24 targets are sampled, with six deterministic one-bit perturbations per target.

For every perturbation we compare:

1. frozen S2 from the corrupted primary state;
2. M1 with the primary corrupted but mirror intact;
3. M1 with the same bit corrupted in both primary and mirror.

The declared recovery gate requires at least `+15 percentage points` absolute gain over S2 on **every** confirmation corpus.

The co-corruption control requires its absolute gain over S2 to stay within `5 percentage points`.

## Result

Portable 9-decimal evidence summary:

- all `9 / 9` corpora meet the recovery-gain gate;
- minimum recovery gain vs S2: `+18.75 pp`;
- mean recovery gain vs S2: about `+29.40 pp`;
- maximum absolute co-corruption gain vs S2: about `3.47 pp`;
- mean transition-cost ratio vs S2: about `1.438×`;
- maximum transition-cost ratio: about `1.886×`.

By size, mean one-bit recovery moves approximately:

```text
5×5: S2 66.44% -> M1 88.89%   (+22.45 pp)
7×7: S2 47.22% -> M1 76.62%   (+29.40 pp)
9×9: S2 22.45% -> M1 58.80%   (+36.34 pp)
```

The gain grows with the tested lattice size, but this suite is not sufficient to claim an asymptotic scaling law.

## Co-corruption falsification

When the same bit is corrupted in both the primary and mirror planes, the recovery gain collapses to at most about `3.47 pp` over S2.

This is the key causal control:

```text
independent mirror survives -> large recovery gain
mirror fails with primary   -> gain mostly disappears
```

So the evidence supports the mirror plane as the source of the recovery improvement rather than an unrelated change in S2 dynamics.

## Adaptation / recommit gate

A mirror that only preserves the past would be a lock, not reflective memory.

For both directions:

```text
A -> C with sustained +0.7 stimulus
C -> A with sustained -0.7 stimulus
```

and for `5×5`, `7×7`, and `9×9`, the primary reaches the new uniform state and the mirror recommits to it after the declared delay.

All six adaptation cases pass.

## Gates

```text
recovery gain >= +15 pp on every corpus      PASS
co-corruption control <= 5 pp                PASS
persistent-state recommit                    PASS
gamma=0 S2 equivalence                       PASS (unit invariant)
M1 reflective recovery gate                  PASS
```

## Cost and claim boundary

Recovery is not free.

M1 adds a second phase plane plus a stability counter per cell, and transition activity is higher than S2 during the tested recovery sequences.

Therefore the result is:

> **internal delayed redundancy improves one-bit recovery on the frozen S2 attractor corpus while preserving the ability to adopt a new persistent state.**

It is **not**:

- a proof of consciousness or self-awareness;
- a quantum-computing result;
- a physical-material implementation;
- a proof of general computational superiority;
- a replacement for the still-open attractor/codebook robustness question.

## Portable evidence identity

As established by S2, raw float-heavy diagnostic JSON is not a cross-runtime identity.

The normative M1 evidence envelope quantizes scientific float fields to 9 decimal places before canonical hashing.

Portable evidence digest:

```text
9479a44ed02e09c9aaa5b51566e296c9119b98e8cd7fcbc9c9551024afadd9a2
```

CI regenerates the full diagnostic report once, derives the portable summary from that report, and compares the committed summary byte-for-byte.
