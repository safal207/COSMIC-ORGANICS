# P1 — MORPHOS-M2 Hierarchical Reflection Results

## Question

Can higher-scale internal self-images recover correlated faults that defeat the single local mirror in M1, without an external target oracle?

## Development selection

The development probe used seeds that are excluded from confirmation. Domain and system couplings shared one value; local M1 coupling remained frozen at `0.15`.

```text
candidate 0.06  FAIL  all-corruption control reached 6.25 pp
candidate 0.08  PASS  first development candidate satisfying every gate
```

`0.08` was frozen before confirmation. No confirmation result was used to retune it.

## Fresh frozen confirmation

Nine new SHA-256 corpora were evaluated: three each at 5×5, 7×7, and 9×9, with 144 deterministic one-bit recovery trials per corpus.

Across the nine corpora, M2 produced substantial **mean** improvements:

- primary-only gain over M1: about `+10.96 pp`;
- primary + local-mirror fault gain over M1 co-corruption: about `+30.71 pp`;
- domain-only surviving-evidence gain over M1 co-corruption: about `+19.37 pp`;
- system-only surviving-evidence gain over M1 co-corruption: about `+18.21 pp`.

This improvement is not free:

- mean primary transition-cost ratio vs M1: about `1.119×`;
- mean double-fault transition-cost ratio vs M1 co-corruption: about `1.634×`;
- maximum double-fault transition-cost ratio: about `2.056×`.

## Strict gates — FAIL

The predeclared requirement was uniform transfer across every frozen corpus, not positive averages.

Observed boundaries:

```text
primary gain >= +5 pp on every corpus          FAIL  minimum +4.17 pp
double-fault gain >= +15 pp on every corpus   FAIL  minimum +12.50 pp
domain-only gain >= +5 pp on every corpus     FAIL  minimum +3.47 pp
system-only gain >= +5 pp on every corpus     FAIL  minimum +0.69 pp
all-corruption |gain vs S2| <= 5 pp           FAIL  maximum 6.25 pp
adaptation / recommit all levels               PASS
full M2 gate                                   FAIL
```

The weakest transfer appears in fresh 5×5 corpora. One 7×7 corpus also exceeded the all-corruption-control limit by `1.25 pp`.

## What the failure means

M2 is not a general hierarchical self-repair result. The stronger statement is rejected.

The supported statement is narrower:

> Hierarchical reflection substantially improves mean correlated-fault recovery on this frozen suite, especially on the larger tested lattices, but the improvement is not uniformly reliable across fresh corpora.

This matters because the failure is not repaired by hiding a corpus or increasing mirror strength. The development law is preserved exactly, and the confirmation boundary becomes evidence.

## Causal interpretation

The higher-scale mirrors still provide useful evidence: when one survives a correlated primary/local fault, recovery often rises sharply. When all mirror planes are corrupted with the primary, the advantage mostly collapses toward S2.

However, surviving evidence is not sufficient for guaranteed recovery. Some attractors remain difficult to disambiguate even when a higher-scale self-image is intact.

That points back to the earlier causal target: **attractor/codebook geometry**.

A plausible next falsifiable question is:

```text
Does minimum distance between stable attractors predict which M2 recovery
trials succeed or fail better than mirror level alone?
```

The next experiment should therefore measure Hamming-distance structure, nearest-attractor collisions, and correctable basin radius before adding another reflection level or increasing coupling.

## Portable evidence

Schema:

`cosmic-organics/multimirror-summary-0.2`

Portable evidence digest:

`3581295f14c6c3013dd991d426eab4a54e13d919959937776208493e5248ff43`

The portable envelope records the frozen mechanism, confirmation corpus identities, strict PASS/FAIL gates, and quantitative boundaries. The full diagnostic report remains reproducible but is not itself the cross-runtime identity.

## Scientific boundary

These are deterministic software toy-model results. They do not demonstrate consciousness, quantum error correction, quantum measurement, physical material self-repair, biological cognition, or general computational superiority.
