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
- [ ] Add broader baseline comparisons (cellular automaton / recurrent model).
- [ ] Measure state capacity, convergence cost, and transition efficiency beyond the current robustness map.
- [ ] Add 2D lattice and heterogeneous cell types.
- [x] Create machine-readable experiment manifests and deterministic result digests.

**Current P1 evidence:**

1. local coupling improves the declared `defect-repair` toy task from `0.8571` to `1.0000`;
2. MORPHOS-0 fails locked temporal subthreshold integration;
3. MORPHOS-T1 repairs that same locked sequence (`1.0000` vs `0.0000`) while zero-input, isolated-pulse, and alternating-pulse negative controls remain stable at the declared temporal configuration;
4. a 400-point robustness sweep finds 20 configurations (`5%`) that pass temporal accumulation, defect repair, and all three negative controls simultaneously.

The robustness result is deliberately classified as **narrow, not global**. The original temporal configuration passes its temporal task but fails the stricter combined spatial+temporal gate because `coupling=0.35` is insufficient for the locked defect-repair task.

These are computational toy-model results, not physical or neural-network superiority claims.

**Exit criterion:** MORPHOS must beat or reveal a distinct useful property versus at least one simple baseline on a declared benchmark. The narrow criterion is met, and a bounded robustness region now exists, but P1 remains open until broader baselines, state capacity, and higher-dimensional/heterogeneous tests are added.

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
