# MORPHOS Cell v0.1

A MORPHOS cell is the smallest stateful unit in the reference model.

## State

```text
phase: A | M | C
energy: non-negative scalar proxy
transitions: integer history counter
```

## Numerical embedding

```text
A = 0.0
M = 0.5
C = 1.0
```

The embedding is an ordering coordinate, not a claim about a named material's crystallinity fraction.

## Neighborhood

MORPHOS-0 uses a one-dimensional lattice. Interior cells have two neighbors; edge cells have one.

## Drive

```text
drive = stimulus + coupling * (neighbor_mean - current_value)
```

## State update

```text
if drive >= crystallize_threshold:
    A -> M -> C
elif drive <= -amorphize_threshold:
    C -> M -> A
else:
    hold
```

Only one structural step can occur per tick.

## Invariants

1. Phase is always one of `A`, `M`, `C`.
2. Energy proxy is non-negative.
3. Transition count never decreases.
4. One tick changes phase by at most one adjacent step.
5. Given identical initial state, parameters, and stimuli, the state digest is deterministic.
