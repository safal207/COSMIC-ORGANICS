# MORPHOS-S2 — Hierarchical Scale Dynamics

**Status:** HYPOTHESIS / computational falsification layer  
**Scope:** software reference model only

## Problem

MORPHOS-S1 repaired the sampled capacity/cost side of the 7×7 / 9×9 generalization failure by weakening all nearest-neighbor coupling with one scale law:

```text
k_s1(L) = k0 * (5 / L)^0.25
```

That same weakening also reduced one-bit recovery as lattice size increased.

S2 asks whether interaction can have two simultaneous scales:

```text
same-domain edge      stronger with scale
cross-domain edge     remains at S1 strength
```

without choosing separate parameters for 5×5, 7×7, and 9×9.

## Fixed local domains

The lattice is partitioned into deterministic square domains with fixed `domain_size = 3` cells per axis.

For cell `(r, c)`:

```text
domain(r, c) = (floor(r / 3), floor(c / 3))
```

Partial edge domains are allowed. Domain assignment is geometry only; it does not depend on observed state or the confirmation corpus.

## Hierarchical law

S1 first supplies the globally scaled coupling `k_s1(L)`.

S2 then applies one additional factor only to nearest-neighbor edges whose endpoints are in the same domain:

```text
h(L) = (L / 5)^beta

same-domain contribution  = h(L) * delta_neighbor
cross-domain contribution = 1.0  * delta_neighbor
```

The cell drive remains degree-normalized over the original local neighborhood.

At the reference size:

```text
h(5) = 1
```

therefore S2 is exactly S1 at 5×5.

## Discovery rule

`beta` is selected from a declared grid before confirmation.

The selection rule is:

> choose the **maximum** hierarchy exponent that preserves a strictly positive sampled binary-capacity delta versus majority CA and a seed-transition-cost ratio below one on every discovery corpus.

This intentionally maximizes local repair pressure only inside the capacity and cost envelope. Recovery labels are not used to select `beta`.

## What S2 can and cannot establish

A PASS can show only that this declared hierarchical software mechanism changes the sampled capacity/recovery/cost tradeoff under the frozen protocol.

It does **not** establish:

- a physical material scaling law;
- physical energy efficiency;
- exhaustive Shannon/channel capacity;
- biological morphogenesis;
- neural-network superiority;
- scale-invariant recovery in untested geometries.

`binary_capacity_bits` remains `log2` of sampled binary fixed attractors. Transition count remains an algorithmic proxy, not physical energy.
