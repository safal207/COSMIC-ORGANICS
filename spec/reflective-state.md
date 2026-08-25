# MORPHOS-M1 — Reflective State Dynamics

Status: **HYPOTHESIS / computational toy model**

MORPHOS-M1 asks whether an internal, lagged self-image can improve recovery from local perturbations without an external target oracle.

## State

M1 carries two phase planes:

\[
S_t = \text{primary state}
\]

\[
R_t = \text{mirror / last committed self-image}
\]

The mirror starts as a copy of the primary state. During ordinary computation the primary evolves under the frozen S2 hierarchical dynamics. The mirror contributes one additional local drive:

\[
d^{mirror}_i = \gamma \left(q(R_i)-q(S_i)\right)
\]

with frozen `gamma = 0.15`.

The mirror is **not** told which state is correct. It only updates after the corresponding primary cell has remained unchanged for `commit_delay = 3` ticks.

## Commit rule

For cell `i`:

```text
if primary_i changed:
    stable_count_i = 0
else:
    stable_count_i += 1

if stable_count_i >= 3 and mirror_i != primary_i:
    mirror_i = primary_i
```

This creates a delayed self-image rather than an immutable golden copy.

## Design constraint

The frozen mirror coupling `0.15` is below half of the smallest binary A/C threshold (`0.35 / 2 = 0.175`). Therefore the mirror term alone cannot force a one-step A↔C correction. It biases the existing S2 dynamics rather than replacing them with a direct target assignment.

The parameter was frozen after a non-evidence development probe. The committed confirmation corpora are separate.

## Falsification controls

M1 is not considered evidence of reflective recovery unless all of the following hold:

1. one-bit primary-only perturbations recover materially better than S2 on every frozen confirmation corpus;
2. co-corrupting the primary and mirror removes almost all of that gain;
3. a persistent external stimulus can move the primary to a new state and the mirror subsequently recommits to it;
4. `gamma = 0` preserves S2 primary dynamics.

The co-corruption control is load-bearing. If the primary and mirror fail together and recovery remains equally strong, the mirror is not explaining the gain.

## Cost boundary

M1 adds redundancy:

- one additional A/M/C mirror plane;
- one integer stability counter per cell;
- additional transition activity may occur during recovery.

This experiment does not claim free error correction.

## Scientific boundary

The words *mirror*, *reflection*, and *self-image* are algorithmic. M1 does not model consciousness, biological self-awareness, quantum measurement, or a physical material device.

Its narrow claim is testable:

> Can delayed internal redundancy improve recovery while remaining able to adopt a genuinely new persistent state?
