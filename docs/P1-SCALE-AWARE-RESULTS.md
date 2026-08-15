# P1 — MORPHOS-S1 Scale-Aware Results

**Suite:** `p1-scale-aware-v0.1`  
**Status:** computational evidence / HYPOTHESIS  
**Result digest:** `87fcf34923727eca1f6129014b53796695b82d05055e708a06fb0d8cdc7c115a`

## Question

The previous Generalization Gate showed a clean failure: the frozen 5×5 MORPHOS-2D-H constants did not preserve sampled binary-capacity advantage at 7×7 and 9×9.

MORPHOS-S1 asks whether one fixed scale law can repair that failure **without choosing separate couplings per lattice size**.

## Discovery

The declared exponent grid contains nine values from `0.00` through `0.40`.

Each exponent is evaluated on nine discovery corpora: three at each of 5×5, 7×7 and 9×9.

A candidate is admissible only if every discovery corpus has:

```text
binary_capacity_delta_bits > 0
seed_transition_cost_ratio < 1
```

The first admissible exponent is:

```text
alpha = 0.25
```

At `alpha = 0.20`, the worst discovery capacity delta is still negative (`-0.1031 bits`). At `alpha = 0.25`, the minimum discovery capacity delta becomes positive (`+0.1375 bits`) while the maximum seed-transition-cost ratio remains `0.3656×`.

The selected scale law is then frozen before confirmation.

## Confirmation

Nine fresh SHA-256-generated confirmation corpora are used: three each for 5×5, 7×7 and 9×9.

Across all nine:

- sampled binary-capacity delta vs majority CA is positive;
- seed-transition-count cost ratio is below one;
- one-bit recovery is **not** consistently equal or better than majority CA.

The frozen non-scale-aware candidate has five non-positive capacity-delta corpora on the same confirmation surface. MORPHOS-S1 has zero.

### Mean by lattice size

| Size | capacity delta | recovery delta | seed-cost ratio | recovery-cost ratio |
|---|---:|---:|---:|---:|
| 5×5 | `+0.4256 bits` | `-4.81 pp` | `0.4126×` | `0.0872×` |
| 7×7 | `+0.5271 bits` | `-34.35 pp` | `0.2540×` | `0.0445×` |
| 9×9 | `+1.2336 bits` | `-54.55 pp` | `0.1387×` | `0.0200×` |

Overall means across the nine confirmation corpora:

```text
capacity delta:       +0.7288 bits
recovery delta:       -31.24 pp
seed-cost ratio:       0.2684×
recovery-cost ratio:   0.0506×
```

## Gate result

```text
scale-capacity gate:       PASS
recovery gate:             FAIL
full scale generalization: FAIL
```

This is a targeted repair, not a broad victory.

The evidence supports a stronger statement than the previous 5×5-only result:

> A fixed scale-aware coupling law can preserve the observed capacity/cost side of the Pareto tradeoff across the declared 5×5, 7×7 and 9×9 corpora.

But the same evidence makes a second statement less favorable:

> As the lattice grows, the selected law increasingly sacrifices one-bit recovery.

That negative result remains load-bearing.

## Causal interpretation

The Generalization Gate moved the first meaningful divergence from a scalar cell threshold to the relationship between local interaction strength and system scale.

MORPHOS-S1 repairs that divergence only partially.

The next refactor point is therefore a **two-objective structural mechanism** capable of keeping enough local interaction for recovery while preventing the large-scale over-smoothing that suppresses attractor diversity.

Candidate next hypotheses include degree-aware or hierarchical coupling, multi-radius interactions, and explicit anchor-domain structure. These must be evaluated under a new frozen discovery/confirmation protocol rather than tuned on the current confirmation corpora.

## Scientific boundary

`binary_capacity_bits` here is `log2` of binary fixed attractors observed from finite sampled inputs. It is not exhaustive information-theoretic channel capacity.

Transition count is an algorithmic state-transition cost proxy. It is not physical energy, latency or device endurance.

MORPHOS-S1 is therefore computational evidence about a toy transition system, not evidence of a fabricated processor or a material scaling law.
