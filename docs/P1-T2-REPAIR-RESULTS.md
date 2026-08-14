# P1 MORPHOS-T2 Mixed-State Repair Results

**Status:** partial repair / no demonstrated dominance

MORPHOS-T2 adds one explicit hypothesis to T1: cells in the intermediate `M` state may use a lower, separately declared relaxation threshold. The goal is to test whether the `mixed-state dead zone` can be reduced without breaking the five already locked temporal/spatial gates.

## Declared grid

The repair suite evaluates 243 combinations:

`memory_decay × threshold × coupling × pulse_amplitude × mixed_relax_threshold`

with three declared values for each dimension.

Before capacity/noise metrics are calculated, every point must pass all five existing gates: subthreshold accumulation, defect repair, zero-input stability, isolated-pulse decay, and alternating-pulse cancellation.

## Result

- `85 / 243` points pass all five old gates (`34.98%`).
- `8` passing points fully remove the mixed-state dead zone on the declared one-bit corruption test.
- `57` passing points beat majority CA on recovery rate alone.
- `6` passing points match or exceed majority CA on both capacity and recovery.
- **0** passing points match/exceed majority CA on capacity and recovery while also matching its transition cost.

### Capacity-matched candidate

`decay=0.4, threshold=0.25, coupling=0.25, pulse=0.2, mixed_threshold=0.05`

- capacity: `4.0` bits — tie with majority CA;
- one-bit recovery: `37.5%` — tie;
- mixed dead-zone: `7.14%`;
- average relaxation transition cost: `2.5` vs majority CA `1.7321`.

### Recovery-biased candidate

`decay=0.4, threshold=0.35, coupling=0.5, pulse=0.25, mixed_threshold=0.05`

- capacity: `3.585` bits (`12` stable states);
- one-bit recovery: `45.24%` — above majority CA `37.5%`;
- mixed dead-zone: `9.52%`;
- average transition cost: `4.9048` — much higher than majority CA.

### Dead-zone-free candidate

A declared passing point reaches `100%` one-bit recovery and `0%` mixed dead-zone, but only by retaining two stable states (`1.0` bit capacity).

## Interpretation

T2 shows that the dead zone is **repairable as a rule-level phenomenon**, but the present repair does not establish a superior memory system. The candidate frontier exposes a three-way tradeoff between capacity, recovery, and transition cost.

This matters because the next architecture should not optimize one metric in isolation. A future MORPHOS variant must either move the Pareto frontier beyond simple baselines or demonstrate a different useful system property.

Grid digest: `883334d7deaaeaa05c3cf304bed6b2b681e42aaea5312206b29a63242afaa03a`.

Result digest: `e70a5547ca58c0601e796dd233922bbc2580470629c830f5f1d9b2bbe38d370d`.
