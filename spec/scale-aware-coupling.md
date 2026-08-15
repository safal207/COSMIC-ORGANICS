# MORPHOS-S1 — Scale-Aware Coupling

**Status:** HYPOTHESIS / computational specification  
**Scope:** software toy model only  
**Physical calibration:** none

## Problem

The frozen MORPHOS-2D-H candidate produced a reproducible 5×5 Pareto point, but the Generalization Gate showed that reusing the same local coupling constants at 7×7 and 9×9 does not preserve the observed binary-capacity advantage.

MORPHOS-S1 tests a narrower causal hypothesis:

> The relevant defect is not the local A/M/C transition rule itself, but treating the interaction strength as independent of the linear scale of the lattice.

## Scale law

Let `k0` be the frozen 5×5 coupling for a cell class and let `L = max(width, height)`.

MORPHOS-S1 applies one fixed law:

```text
k_eff(L) = k0 * (L_ref / L)^alpha
```

with:

```text
L_ref = 5
alpha = 0.25
```

The same factor is applied to both frozen checkerboard cell classes:

```text
anchor:   0.75 * factor(L)
adaptive: 0.50 * factor(L)
```

Thresholds, mask, neighborhood, relaxation rule and memory setting remain unchanged.

At the reference size:

```text
factor(5) = 1
```

so MORPHOS-S1 is exactly the frozen 5×5 coupling rule rather than a newly tuned 5×5 candidate.

## Selection discipline

`alpha` is not chosen separately for 5×5, 7×7 and 9×9.

A declared discovery grid is evaluated:

```text
0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40
```

across nine discovery corpora: three independent SHA-256-generated corpora at each of 5×5, 7×7 and 9×9.

The selection rule is fixed before confirmation:

```text
choose the minimum alpha such that, on every discovery corpus:

binary_capacity_delta_bits > 0
and
seed_transition_cost_ratio < 1
```

The first admissible value is `alpha = 0.25`.

Confirmation then uses nine different corpora. No exponent or per-size coupling is changed after those confirmation inputs are declared.

## What S1 is allowed to prove

If confirmation passes the declared capacity/cost gate, the supported claim is only:

> A single power-law coupling rule can remove the observed sampled binary-capacity scaling failure of the frozen MORPHOS candidate across the declared 5×5/7×7/9×9 confirmation corpora while retaining lower transition-count cost.

It does **not** prove:

- exhaustive channel capacity;
- scale invariance at arbitrary lattice sizes;
- superior error correction;
- lower physical energy;
- a physical law of material coupling;
- a neural, biological or quantum advantage.

## Current result

The scale-capacity gate passes on all nine confirmation corpora, but the recovery gate fails.

The next causal question is therefore no longer only:

```text
how should coupling depend on scale?
```

It becomes:

```text
how can structural capacity and self-recovery co-scale without collapsing into over-smoothing or near-independent cells?
```
