# P1 Baseline Results v0.1

**Status:** HYPOTHESIS TEST / toy computational benchmark

This document records the first falsification-oriented comparison for MORPHOS-0. It is not evidence of superiority over neural networks, physical phase-change hardware, or conventional processors.

## Controlled baseline

The baseline is deliberately narrow: it uses the **same three-state transition machine, same thresholds, same initial state, and same stimuli**, but forces neighborhood coupling to `0`.

This isolates one question:

> Does local structural interaction provide a measurable computational property that independent stateful cells do not provide in the same toy model?

## Results

| Benchmark | MORPHOS accuracy | Baseline accuracy | Delta | Criterion |
|---|---:|---:|---:|---|
| defect-repair | 1.0000 | 0.8571 | +0.1429 | PASS |
| pulse-retention | 1.0000 | 1.0000 | 0.0000 | PASS |
| subthreshold-accumulation | 0.0000 | 0.0000 | 0.0000 | **FAIL** |

Result digest:

`09f54bbb9d49654ab2c3671f8486af67aaf4b287ae6edfa99a54fb5d488f0a1f`

## What was learned

### 1. Local interaction exposes a useful property

With an initial state `CCCACCC`, no external drive, coupling `1.0`, crystallization threshold `0.4`, and amorphization threshold `1.2`, MORPHOS repairs the central defect in two ticks:

```text
CCCACCC -> CCCMCCC -> CCCCCCC
```

The uncoupled baseline remains `CCCACCC`.

This is evidence only for **spatial error repair inside the declared model**. The asymmetric thresholds are an explicit modeling choice and must later be calibrated or rejected against a named physical device.

### 2. Persistence is not an interaction advantage

Both MORPHOS and the uncoupled stateful baseline retain the completed `CCCCC` state after the pulse is removed. This demonstrates memory in the coarse state machine, but does not demonstrate a coupling advantage.

### 3. Temporal integration currently fails

Five repeated pulses of `0.2` do not cross a `0.35` threshold because MORPHOS-0 stores the latest drive as an energy proxy but does not feed retained energy/history back into the next transition equation.

That failure is valuable: it identifies the next concrete model change to test—**a decaying accumulation / hysteretic memory term**—and gives us a regression target that must not be “passed” by changing the benchmark after the fact.

## Validation assessment

**Share with caveats.** The benchmark is deterministic and reproducible, the comparison holds all declared variables except coupling constant, and the committed result is regenerated in CI. However:

- the benchmark space is tiny and hand-designed;
- thresholds are dimensionless and not calibrated to a material;
- there is no statistical robustness analysis yet;
- the baseline is an ablation baseline, not a competitive neural or cellular-automaton architecture;
- “defect repair” must not be generalized into claims of intelligence, self-healing matter, or hardware superiority.

## Next falsification target

Add a retained internal activation variable with explicit decay, then rerun the **unchanged** subthreshold-accumulation benchmark plus new negative controls. The desired result is not merely a PASS: the new mechanism must avoid spontaneous transitions under zero input and must expose its additional transition/energy cost.
