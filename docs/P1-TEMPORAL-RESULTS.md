# P1 Temporal Memory Results v0.1

**Status:** HYPOTHESIS TEST / experimental computational extension

MORPHOS-T1 tests the specific failure discovered in `p1-baseline-v0.1`: MORPHOS-0 could not integrate repeated subthreshold pulses over time.

The original five-pulse sequence is **locked and unchanged**:

```text
0.2, 0.2, 0.2, 0.2, 0.2
```

with a transition threshold of `0.35`.

## Mechanism under test

MORPHOS-T1 adds one signed internal variable per cell:

\[
a_{t+1}=\lambda a_t + d_t
\]

where:

- `a_t` is retained activation;
- `lambda` is `memory_decay` (`0.8` in this suite);
- `d_t` is the same instantaneous stimulus + neighborhood drive used by the coarse transition model.

When a phase transition occurs, activation is reset to zero in this experiment.

**Important:** retained activation is an algorithmic state. It is not claimed to be physical energy, charge, temperature, or any other measurable material quantity until a later calibration step maps it to a named device.

## Result

| Benchmark | MORPHOS-T1 | MORPHOS-0 baseline | Result |
|---|---:|---:|---|
| locked subthreshold accumulation | 1.0000 | 0.0000 | PASS |
| zero-input stability | 1.0000 | 1.0000 | PASS |
| isolated pulse decay | 1.0000 | 1.0000 | PASS |
| alternating pulse cancellation | 1.0000 | 1.0000 | PASS |

Result digest:

`d345bb2217df6e4414ca1faedc4780a780b0f0ac8366812f83b8d61143ae9ed0`

The locked accumulation sequence drives each cell through `A -> M -> C`, while MORPHOS-0 remains `A` because it has no retained activation.

## Why the negative controls matter

A temporal accumulator could trivially “solve” accumulation if it also caused uncontrolled drift. Three controls therefore stay in the suite:

1. zero input must cause zero transitions;
2. one isolated `0.2` pulse must decay without delayed transition;
3. alternating `+0.2 / -0.2` pulses must not ratchet the state upward.

All three pass in v0.1.

## Validation assessment

**Share with caveats.** This is a clean software ablation: the pulse sequence and thresholds are held fixed, the only new capability is retained activation, and negative controls are explicit. But it is still a toy model.

Remaining risks:

- `memory_decay=0.8` is hand-selected, not experimentally fitted;
- reset-on-transition is a modeling choice;
- parameter sensitivity has not yet been mapped;
- no noise or stochastic drift is present;
- no physical energy/cost model exists;
- no competitive recurrent-neural baseline has been tested.

## Next gate

Run a parameter sweep over decay, thresholds, coupling, and pulse amplitude; define robustness regions rather than single-point success. After that, add a small recurrent baseline and compare memory capacity versus transition cost.
