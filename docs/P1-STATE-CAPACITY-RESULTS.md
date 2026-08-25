# P1 State Capacity Results

**Status:** negative / diagnostic computational result

This suite measures a narrow binary memory question on a seven-cell lattice: how many `A/C` patterns remain unchanged after three zero-input relaxation ticks, and what happens after a single-bit corruption.

The declared MORPHOS configuration keeps the temporal parameters from the known all-gate robustness point (`memory_decay=0.8`, threshold `0.35`) while sweeping coupling across `0.0`, `0.25`, `0.5`, and `1.0`.

## Capacity tradeoff

| coupling | stable states / 128 | capacity bits | one-bit recovery | mixed dead-zone |
|---:|---:|---:|---:|---:|
| 0.00 | 128 | 7.0 | 0.0% | 0.0% |
| 0.25 | 16 | 4.0 | 0.0% | 82.14% |
| 0.50 | 2 | 1.0 | 0.0% | 100.0% |
| 1.00 | 2 | 1.0 | 0.0% | 100.0% |

The `coupling=1.0` configuration is the coupling value used by the known all-gate robustness point. Under this state-capacity test it retains only the two uniform binary states (`AAAAAAA` and `CCCCCCC`).

An important detail exposed by CI is that the temporal accumulator changes the capacity boundary: even at `coupling=0.25`, repeated zero-input neighbor drive is retained across ticks and collapses the stable set from 128 states to 16. The state-capacity runner therefore measures the actual MORPHOS-T1 dynamics, not a memoryless approximation.

## External baselines

- **Independent binary memory:** 128 stable states (7 bits), 0% error recovery, zero relaxation transitions.
- **Nearest-neighbor majority CA:** 16 stable states (4 bits), 37.5% recovery of single-bit corruptions, average 1.7321 state transitions per corruption trial.
- **MORPHOS robust configuration:** 2 stable states (1 bit), 0% recovery, average 5.2857 transitions, and a mixed-state dead zone in 100% of corruption trials over its stable codebook.

## Interpretation

This is evidence **against** a state-capacity or noise-recovery advantage for the current MORPHOS-T1 rule. Strong coupling improves the earlier locked defect-repair task, but it also collapses the number of retained patterns. More importantly, single-bit corruption produces intermediate `M` cells that no longer resolve under the declared relaxation window.

That failure mode is now named **mixed-state dead zone**.

The result does not imply that every possible MORPHOS transition rule has low capacity. It shows that the current rule and declared parameter regime do. A future rule change must repair this failure without deleting the already locked temporal, robustness, and negative-control evidence.

Result digest: `02512286be42f99908a6bf2bc07d4f7fb4fc03853fa04e9e172dd2b4f5b09a5b`.
