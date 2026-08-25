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
- [x] Add a 5×5 2D lattice with checkerboard heterogeneous cell types and frozen confirmation corpus.
- [x] Produce a reproducible Pareto point that survives a separate confirmation corpus.
- [x] Test the frozen 2D point across five unseen 5×5 seeds, larger lattices, mask/neighborhood ablations, multi-bit noise, and a stronger local recurrent threshold baseline.
- [x] Introduce MORPHOS-S1 with one fixed scale-aware coupling law selected on a declared discovery grid and frozen before confirmation.
- [x] Repair the sampled binary-capacity scaling failure across nine fresh 5×5/7×7/9×9 confirmation corpora without per-size retuning.
- [ ] Recover error-correction quality across scale while retaining S1's capacity and transition-cost behavior.
- [ ] Test a learned reservoir / associative-memory baseline on a frozen protocol.
- [ ] Map the software transition-cost proxy to a physical-device cost model.
- [x] Create machine-readable experiment manifests and deterministic result digests.

**Current P1 evidence:**

1. local coupling improves the declared `defect-repair` toy task from `0.8571` to `1.0000`;
2. MORPHOS-0 fails locked temporal subthreshold integration;
3. MORPHOS-T1 repairs that same locked sequence while its declared negative controls remain stable;
4. a 400-point robustness sweep finds only a narrow all-gate region (`20 / 400`);
5. simple task-matched external baselines tie all three original positive toy tasks;
6. state-capacity testing exposes a mixed-state dead zone and no capacity/noise advantage for T1;
7. T2 partially repairs that failure but **0** T2 points dominate majority CA on capacity + recovery + transition cost together;
8. 2D checkerboard heterogeneity survives a frozen 256-input SHA-256 confirmation corpus as a non-dominated Pareto point;
9. the same frozen 5×5 candidate repeats its capacity/cost-biased tradeoff across five unseen seeds, but direct 7×7/9×9 scale transfer fails;
10. 1/2/3-bit corruption remains cheaper but less accurately recovered than majority CA;
11. a local recurrent threshold challenge does not dominate the frozen MORPHOS point, but MORPHOS does not dominate that frontier either;
12. MORPHOS-S1 selects the minimum admissible exponent `alpha = 0.25` from a declared discovery grid using one fixed law `k_eff = k0 * (5/L)^alpha`;
13. on nine new confirmation corpora, the frozen non-scale-aware candidate has `5` non-positive capacity deltas while S1 has `0`; mean S1 capacity delta is `+0.7288 bits` and mean seed-transition-cost ratio is `0.2684×`;
14. S1 does **not** solve recovery scaling: mean one-bit recovery delta is `-31.24 pp`, so full scale generalization remains FAIL.

These are computational toy-model results, not physical, biological, quantum, or neural-network superiority claims.

**Exit criterion:** P1 remains open. MORPHOS-S1 repairs the sampled capacity/cost side of the larger-grid scaling failure under a frozen confirmation protocol, but recovery quality degrades strongly with scale. The next architecture must co-scale **capacity + recovery**, not merely weaken local coupling further. A learned reservoir/associative baseline should also be added before any broad computational-advantage claim.

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
