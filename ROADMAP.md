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
- [ ] Add broader baseline comparisons (cellular automaton / recurrent model).
- [ ] Measure convergence, transition cost, memory retention, robustness, and state capacity across parameter sweeps. (`transition_count`, retention, and accuracy are present in v0.1; robustness/state capacity are not.)
- [ ] Add 2D lattice and heterogeneous cell types.
- [x] Create a machine-readable experiment manifest and deterministic result digest.
- [x] Preserve a known failing benchmark (`subthreshold-accumulation`) instead of tuning it away.

**Current P1 evidence:** local coupling improves the declared `defect-repair` toy task from `0.8571` to `1.0000`, while temporal subthreshold integration fails. This is a partial computational result, not a physical or neural-network superiority claim.

**Exit criterion:** MORPHOS must beat or reveal a distinct useful property versus at least one simple baseline on a declared benchmark. Failure is a valid research result. The v0.1 ablation meets the narrow “distinct property” criterion for defect repair; P1 remains open until robustness and broader baselines are tested.

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
