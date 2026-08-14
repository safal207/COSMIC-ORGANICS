# P1 External Baseline Results v0.1

**Status:** HYPOTHESIS / falsification evidence

The earlier P1 experiments compared MORPHOS against ablated versions of itself. That establishes mechanism effects, but it does not establish that the behavior is unique or computationally advantageous.

This suite therefore adds simple **external, task-matched algorithmic baselines**.

## Baselines

### Defect repair — MajorityCA

The locked spatial task starts from:

```text
CCCACCC
```

and targets:

```text
CCCCCCC
```

A binary nearest-neighbor majority cellular automaton updates each cell from its local neighbors; ties preserve the current state.

Result:

- MORPHOS-0 accuracy: `1.0`
- MajorityCA accuracy: `1.0`
- outcome: **tie**

MajorityCA uses a direct `A -> C` binary update while MORPHOS traverses `A -> M -> C`, so raw transition counts are not directly comparable as physical cost.

### Pulse retention — minimal threshold state machine

A minimal three-state software machine with no retained activation (`memory_decay=0`) receives the same strong pulse sequence.

Result:

- MORPHOS-0 accuracy: `1.0`
- baseline accuracy: `1.0`
- outcome: **tie**

### Temporal accumulation — leaky three-state accumulator

A minimal software accumulator uses:

```text
activation[t+1] = 0.8 * activation[t] + pulse[t]
```

with the same `0.35` threshold and reset-on-transition semantics as the declared MORPHOS-T1 temporal experiment.

Result:

- MORPHOS-T1 accuracy: `1.0`
- leaky accumulator accuracy: `1.0`
- outcome: **tie**

## Summary

```text
MORPHOS wins:   0
baseline wins:  0
ties:           3
```

`distinct_advantage_observed = false`

Result digest:

`c3d59a8408c4c7c434c92450b61dd86438d017c61f1ddd9475e3ca2ff8b42e3b`

## Interpretation

This is a useful negative result.

The current tasks demonstrate that MORPHOS mechanisms can produce local repair, persistent state, and temporal integration. They do **not** demonstrate that those capabilities are unique, more efficient, or more powerful than simple conventional algorithms.

The correct next question is no longer “can MORPHOS perform these behaviors?” It is:

> **Can a MORPHOS system expose a measurable property—capacity, robustness, energy/transition cost, heterogeneous adaptation, or another declared capability—that survives comparison with appropriate external baselines?**

Until that happens, claims of a new computational advantage remain unsupported.

These baselines are deliberately small and task-matched; they are not a comprehensive comparison with neural networks, reservoir computing, modern cellular automata, or physical neuromorphic hardware.
