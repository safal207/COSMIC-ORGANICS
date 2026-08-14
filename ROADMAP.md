# Roadmap

## P0 — Foundation

- [x] Define COSMIC ORGANICS scientific status model.
- [x] Specify MORPHOS Protocol v0.1.
- [x] Specify State Algebra v0.1.
- [x] Implement deterministic MORPHOS-0 lattice.
- [x] Add reproducibility digest and unit tests.
- [x] Add evidence map and CI.

## P1 — Computational falsification

- [x] Define 3 benchmark tasks where structural transitions are the only adaptive state.
- [x] Add an uncoupled stateful ablation baseline.
- [x] Preserve the first known failure instead of tuning it away.
- [x] Add MORPHOS-T1 retained activation and repair the locked subthreshold-integration failure with three negative controls.
- [x] Sweep decay, threshold, coupling, and pulse amplitude across a declared 400-point grid.
- [x] Add simple external task-matched baselines (majority cellular automaton / leaky three-state accumulator).
- [x] Measure binary state capacity, retention, single-bit noise recovery, and relaxation transition cost.
- [x] Evaluate a targeted MORPHOS-T2 mixed-state relaxation repair over a declared 243-point grid.
- [ ] Move the capacity/recovery/cost Pareto frontier beyond simple external baselines or identify a genuinely different useful property.
- [ ] Add 2D lattice and heterogeneous cell types.
- [x] Create machine-readable experiment manifests and deterministic result digests.

**Current P1 evidence:**

1. local coupling improves the declared `defect-repair` toy task from `0.8571` to `1.0000`;
2. MORPHOS-0 fails locked temporal subthreshold integration;
3. MORPHOS-T1 repairs that same locked sequence while its declared negative controls remain stable;
4. a 400-point robustness sweep finds only a narrow all-gate region (`20 / 400`);
5. simple task-matched external baselines tie all three original positive toy tasks;
6. state-capacity testing exposes a mixed-state dead zone and no capacity/noise advantage for T1;
7. T2 partially repairs that failure: `85 / 243` repair-grid points preserve all old gates, `8` eliminate the declared dead zone, and `57` beat majority CA on recovery alone — but **0** dominate majority CA on capacity + recovery + transition cost together.

These are computational toy-model results, not physical or neural-network superiority claims.

**Exit criterion:** P1 requires a measurable property that survives appropriate external baselines. T2 demonstrates a tunable capacity/recovery tradeoff but not dominance. The next architecture should test whether heterogeneous or higher-dimensional structure creates a genuinely new Pareto region rather than adding another scalar threshold.

## P2 — Material correspondence

- [ ] Select one named physical device class (PCM, ReRAM/memristive, photonic PCM, ionic/electrochemical).
- [ ] Replace dimensionless transition rules with literature- or experiment-calibrated parameters.
- [ ] Model drift, noise, hysteresis, endurance, and write energy.
- [ ] Compare predicted transitions with published or independently measured device data.

**Exit criterion:** a declared mapping from simulator variables to measurable physical quantities with bounded error.

## P3 — Physical neuro-system

- [ ] Compose heterogeneous calibrated cells into a small network.
- [ ] Demonstrate memory + nonlinear response + task behavior.
- [ ] Produce an independently reproducible evidence bundle.

## P4 — Biointerface research

- [ ] Review non-living biomaterials and biointerface control mechanisms first.
- [ ] Define strict safety, ethics, and experimental governance requirements.
- [ ] Explore whether material-state control can shape a biological environment without making unsupported organ-fabrication claims.

## Horizon

Self-reconfiguring matter, tissue-scale morphogenesis, organ engineering, and quantum-biological mechanisms remain horizon topics until each has a concrete measurable mechanism and evidence path.
