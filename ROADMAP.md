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
- [ ] Repair or intentionally redesign the mixed-state dead zone without invalidating locked evidence.
- [ ] Add 2D lattice and heterogeneous cell types.
- [x] Create machine-readable experiment manifests and deterministic result digests.

**Current P1 evidence:**

1. local coupling improves the declared `defect-repair` toy task from `0.8571` to `1.0000`;
2. MORPHOS-0 fails locked temporal subthreshold integration;
3. MORPHOS-T1 repairs that same locked sequence (`1.0000` vs `0.0000`) while zero-input, isolated-pulse, and alternating-pulse negative controls remain stable at the declared temporal configuration;
4. a 400-point robustness sweep finds 20 configurations (`5%`) that pass temporal accumulation, defect repair, and all three negative controls simultaneously;
5. simple task-matched external baselines tie MORPHOS on all three current positive toy tasks (`0` MORPHOS wins, `3` ties);
6. at the known all-gate coupling (`1.0`), binary state capacity collapses to `2 / 128` stable states (`1.0` bit), single-bit recovery is `0%`, and all corruption trials over that stable codebook terminate with mixed `M` states. Majority CA retains `16 / 128` stable states (`4.0` bits) and recovers `37.5%` of single-bit corruptions.

The robustness result is deliberately classified as **narrow, not global**. The external-baseline and state-capacity results show that the current rule has no demonstrated algorithmic advantage and exposes a concrete mixed-state dead zone.

These are computational toy-model results, not physical or neural-network superiority claims.

**Exit criterion:** P1 requires a task or measurable system property where MORPHOS shows a declared advantage or qualitatively distinct capability against appropriate external baselines. Before moving to stronger claims, the mixed-state dead zone must be resolved or justified, and the result must survive the already locked temporal, robustness, capacity, and negative-control tests.

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
