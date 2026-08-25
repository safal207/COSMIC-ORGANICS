# P1 Robustness Results v0.1

**Status:** HYPOTHESIS / computational evidence

This experiment asks a stricter question than the single-configuration temporal result:

> Does the useful behavior survive across a declared parameter grid while both positive tasks and all negative controls remain satisfied?

## Grid

The sweep is the Cartesian product of:

- `memory_decay`: `0.0, 0.4, 0.6, 0.8, 0.9`
- `crystallize_threshold`: `0.25, 0.35, 0.45, 0.55`
- `coupling`: `0.0, 0.25, 0.35, 0.5, 1.0`
- `pulse_amplitude`: `0.10, 0.15, 0.20, 0.25`

Total: **400 configurations**.

## Locked gates

A configuration is counted as stable only when all five conditions pass:

1. repeated subthreshold pulses reach `CCCCC`;
2. the locked `CCCACCC -> CCCCCCC` defect-repair task succeeds;
3. zero input creates no transition;
4. one isolated pulse decays without a delayed transition;
5. alternating positive/negative pulses do not ratchet the state upward.

The defect task retains its previously declared `amorphize_threshold=1.2`; the swept threshold is the crystallization threshold for that locked task. Other tasks use the swept threshold symmetrically.

## Result

- all-gate stable points: **20 / 400**
- stable fraction: **0.05**
- interpretation: **narrow, not global**

Per-gate pass counts:

| Gate | Passing points |
|---|---:|
| zero-input stability | 400 |
| alternating-pulse cancellation | 375 |
| isolated-pulse decay | 375 |
| subthreshold accumulation | 95 |
| defect repair | 80 |

The full all-gate region occurs only at `coupling=0.5` or `1.0` within this grid. This means the current joint spatial+temporal behavior is sensitive to parameter choice.

The original temporal configuration (`decay=0.8`, `threshold=0.35`, `coupling=0.35`, `pulse=0.2`) still passes temporal accumulation, but it fails the stricter combined gate because the locked defect-repair task does not repair at that coupling.

## Evidence binding

The runner hashes all 400 per-point outcomes into `grid_digest`, then hashes the report into `result_digest`.

- `grid_digest`: `b883f0588c7c0acbc75d765550628a2013f667423c0a7df8baffaf2ee26d9ae2`
- `result_digest`: `e0ff9abbbfdb045692dd809691db51bd77b084d4f59b286afd1b6ccea324ccc5`

CI regenerates the complete report from the manifest and byte-compares it with the committed result artifact.

## Interpretation

This result is evidence **against** a claim of broad robustness. It supports only a narrower claim: within the declared toy model, there is a non-empty bounded region where temporal integration, spatial defect repair, and the negative controls coexist.

No physical device calibration, neural-network superiority, biological function, or quantum mechanism is established by this sweep.

## Next falsification target

The next useful gate is a broader algorithmic baseline comparison, followed by explicit state-capacity and transition-cost measurements. If MORPHOS cannot retain a useful distinction under those comparisons, P1 should remain negative or partial.
