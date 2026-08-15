# MORPHOS-M2 — Hierarchical Reflection

## Status

Algorithmic research mechanism. This specification does not claim consciousness, quantum measurement, physical material implementation, or biological self-awareness.

## Hypothesis

A single reflective plane (M1) can recover some primary-state perturbations, but fails when primary and mirror are corrupted together. M2 asks whether delayed self-images at larger spatial scopes can preserve independent recovery evidence.

## State

Each cell participates in four A/M/C phase planes:

1. primary state;
2. local mirror;
3. domain mirror;
4. system mirror.

The mirrors are not external targets. After initialization they may only be rewritten from primary state that remains stable for the declared commit interval.

## Frozen law

```text
local coupling   = 0.15
local delay      = 3 ticks

domain coupling  = 0.08
domain delay     = 4 ticks

system coupling  = 0.08
system delay     = 5 ticks
```

The domain partition is inherited from S2: fixed 3×3 domains. The primary spatial dynamics remain the frozen S2 law.

For cell `i`, M2 adds three discrepancy terms to the S2 drive:

```text
drive_i = drive_S2_i
        + k_local  * (q(local_i)  - q(primary_i))
        + k_domain * (q(domain_i) - q(primary_i))
        + k_system * (q(system_i) - q(primary_i))
```

## Commit semantics

- Local mirror: a cell may recommit after that primary cell is unchanged for 3 ticks.
- Domain mirror: a whole domain may recommit only after every primary cell in that domain is unchanged for 4 consecutive ticks.
- System mirror: the full system may recommit only after the entire primary plane is unchanged for 5 consecutive ticks.

Therefore higher-level mirrors are slower evidence planes, not permanent immutable copies.

## Development / confirmation separation

The shared domain/system coupling was chosen only on development seeds. Confirmation seeds are disjoint and frozen before evaluation.

Development candidates were `0.06, 0.08, 0.10, 0.12, 0.14, 0.16`.

- `0.06` failed the all-corruption control.
- `0.08` was the first candidate satisfying all development gates and was frozen.
- Larger values were not promoted merely because they were stronger.

No confirmation failure may trigger retuning inside M2 v0.1.

## Causal fault cases

The frozen suite distinguishes:

- primary only corrupted;
- primary + local mirror corrupted;
- primary + local + system corrupted, leaving domain evidence intact;
- primary + local + domain corrupted, leaving system evidence intact;
- primary + all three mirrors corrupted.

The last case is a negative causal control: if every self-image fails with the primary, M2 should collapse near the non-reflective S2 behavior.

## Evidence rule

A full diagnostic report is regenerated in CI. A compact portable scientific envelope quantizes floating-point fields to 9 decimal places before canonical hashing and is compared byte-for-byte with the committed evidence file.

A green CI run means the declared experiment reproduced. It does **not** mean the hypothesis passed; scientific gates are recorded independently inside the evidence envelope.
