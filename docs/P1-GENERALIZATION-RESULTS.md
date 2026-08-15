# P1 Generalization Gate v0.1

**Status:** PARTIAL / gate remains open

This suite freezes the 5×5 checkerboard candidate from the preceding 2D experiment. No candidate thresholds or couplings are retuned here.

## Questions

1. Does the observed capacity/cost Pareto effect repeat across unseen seeds?
2. Does it survive larger grids?
3. Is it specific to checkerboard heterogeneity or four-neighbor geometry?
4. What happens under 2-bit and 3-bit corruption?
5. Does a stronger local recurrent threshold baseline dominate the frozen candidate?

All reported capacities are **sample-observed attractor counts**, not exhaustive physical or mathematical channel capacities.

## Multi-seed transfer — PASS, with the same tradeoff

Five unseen 5×5 SHA-256-generated corpora (64 seeds each) were evaluated.

Across all five:

- candidate binary-capacity delta vs majority CA remained positive;
- candidate one-bit recovery delta remained negative;
- candidate seed-transition cost remained lower.

Mean deltas:

- observed capacity: **+0.3143 bits**;
- one-bit recovery: **−8.56 percentage points**;
- seed-transition cost ratio: **0.3785×** majority CA.

This supports repeatability of the *tradeoff*, not superiority.

## Scaling — FAIL

With the same frozen candidate parameters:

| Grid | Candidate attractors | Majority attractors | Capacity delta | Recovery delta | Seed-cost ratio |
|---|---:|---:|---:|---:|---:|
| 5×5 | 51 | 42 | +0.2801 bits | −5.89 pp | 0.3714× |
| 7×7 | 36 | 40 | −0.1520 bits | −9.42 pp | 0.4360× |
| 9×9 | 19 | 31 | −0.7063 bits | −6.66 pp | 0.4968× |

The observed capacity advantage is therefore **not scale-generalized**. The full scaling gate remains closed.

## Mask and neighborhood ablations

The same thresholds/couplings were reused while changing only cell-class geometry or neighborhood.

- checkerboard keeps the capacity/cost-biased tradeoff;
- row/column stripes can move toward better recovery while sacrificing observed capacity;
- Moore neighborhoods increase the observed capacity gap on the declared sample but further reduce recovery.

This is evidence that **geometry matters**, but not that one topology is universally best.

## Multi-bit noise — accuracy FAIL, cost PASS

At 1/2/3-bit corruption the frozen candidate remains cheaper to relax than majority CA, but recovers fewer targets at every tested corruption level.

| Noise | MORPHOS recovery | Majority recovery | MORPHOS/majority recovery cost |
|---|---:|---:|---:|
| 1 bit | 61.17% | 68.52% | 0.0660× |
| 2 bit | 42.83% | 47.78% | 0.1344× |
| 3 bit | 27.33% | 33.89% | 0.2025× |

Raw transition count remains only an algorithmic cost proxy, not physical energy.

## Recurrent challenge — Pareto status survives

A 15-point grid of local recurrent binary threshold networks was evaluated on a discovery corpus and reduced to **3 behaviorally unique regimes** before confirmation.

On a separate 96-input confirmation corpus:

- no recurrent regime dominates the frozen MORPHOS candidate across observed capacity + one-bit recovery + seed-transition cost;
- MORPHOS also does not dominate all recurrent regimes.

The regimes expose the expected extremes: high recovery with high dynamic cost, or high observed capacity with poor recovery. MORPHOS remains a distinct Pareto point between them.

## Gate result

```text
seed transfer          PASS
larger-grid scaling    FAIL
multi-bit recovery     FAIL
multi-bit cost         PASS
recurrent Pareto       PASS
--------------------------------
full generalization    FAIL
```

Evidence summary digest:

`953e38a05958f970386bd256b964ade1d9240b3ff134da696bf8d9942e9850c0`

Interpretation: **partial seed transfer, new Pareto point, not scale generalization**.

The next architecture should target scale-aware heterogeneity or hierarchical/local-normalized coupling rather than retuning the frozen 5×5 constants.
