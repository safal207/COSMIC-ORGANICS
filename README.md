# COSMIC ORGANICS

**Programmable matter, physical neuro-systems, and verifiable morphogenetic computation.**

COSMIC ORGANICS is an open research program for exploring computation in which material state is not merely storage for a program: **state transition is part of the computation itself**.

The first concrete artifact is **MORPHOS Protocol v0.1** and its reference simulator, **MORPHOS-0**.

> Core model: `state + interaction + constraint + energy + time -> transition -> function`

## Scientific status

Every major claim belongs to one of three classes:

- **VERIFIED** — grounded in established or cited experimental/review literature.
- **HYPOTHESIS** — a falsifiable model proposed by this project.
- **HORIZON** — a long-range direction, not a demonstrated capability.

This repository does **not** claim that COSMIC ORGANICS can currently fabricate organs, create new biological life, or implement a quantum computer. Those are horizon questions that require independent experimental evidence.

## Architecture

```text
COSMIC ORGANICS
├── MORPHOS Protocol       formal state/transition language
├── MORPHOS-0              deterministic reference simulator
├── MORPHOS-T1             experimental temporal-memory extension
├── MORPHOS-T2             mixed-state relaxation experiment
├── MORPHOS-2D-H           2D heterogeneous experiment
├── Generalization Gate    seed / scale / topology / noise / recurrent challenge
├── State Algebra          composition / interaction / delta / ratio
├── Evidence Map           claim -> source -> status
└── Research Horizon       materials -> physical neuro-systems -> biointerfaces
```

## MORPHOS-0

MORPHOS-0 models a one-dimensional lattice of cells with three coarse structural states: `A` amorphous, `M` mixed/intermediate, and `C` crystalline/ordered.

```bash
python -m morphos.simulator
python -m unittest discover -s tests -v
```

## P1 falsification suites

```bash
python -m benchmarks.run
python -m benchmarks.run_temporal
python -m benchmarks.run_robustness
python -m benchmarks.run_external_baselines
python -m benchmarks.run_state_capacity
python -m benchmarks.run_t2_repair
python -m benchmarks.run_2d_heterogeneous
python -m benchmarks.run_generalization
```

The evidence chain intentionally preserves negative results: the first temporal failure, narrow robustness, external-baseline ties, the T1 mixed-state dead zone, T2's capacity/recovery/cost tradeoff, and the current failure to scale the frozen 5×5 constants to 7×7/9×9.

The frozen 5×5 checkerboard candidate previously produced a reproducible new Pareto point versus majority CA. The generalization suite tests that candidate **without retuning**.

Current generalization result:

- across five unseen 5×5 corpora, the observed capacity delta stays positive and transition cost stays lower, but recovery stays lower;
- mean observed capacity delta: `+0.3143 bits`;
- mean one-bit recovery delta: `-8.56 pp`;
- mean seed-transition cost ratio: `0.3785×` majority CA;
- observed capacity advantage survives at 5×5 but fails at 7×7 and 9×9;
- under 1/2/3-bit corruption the candidate is consistently cheaper but less accurate;
- against a 15-point local recurrent threshold challenge reduced to 3 unique regimes, the frozen candidate remains Pareto-nondominated but does not dominate the recurrent frontier.

Therefore the **full generalization gate remains closed**. The current evidence supports a repeatable 5×5 Pareto tradeoff, not scale-general computational superiority.

The seven earlier full result artifacts remain under `results/`; the new Generalization Gate publishes a compact digest-bound summary under `results/p1-generalization-v0.1-summary.json`. CI regenerates the full report and then reproduces that compact summary byte-for-byte.

## Research question

Can useful computation be expressed as controlled transitions of structured, mixed, and amorphous states, such that the computational state is also a persistent physical-like structure?

The software model is only the first test of that question.

## Documents

- [Vision](docs/VISION.md)
- [MORPHOS Protocol v0.1](docs/MORPHOS-PROTOCOL.md)
- [Scientific boundaries](docs/SCIENTIFIC-BOUNDARIES.md)
- [State algebra](spec/state-algebra.md)
- [MORPHOS cell](spec/morphos-cell.md)
- [Evidence map](research/evidence-map.md)
- [P1 baseline results](docs/P1-BASELINE-RESULTS.md)
- [P1 temporal results](docs/P1-TEMPORAL-RESULTS.md)
- [P1 robustness results](docs/P1-ROBUSTNESS-RESULTS.md)
- [P1 external baseline results](docs/P1-EXTERNAL-BASELINE-RESULTS.md)
- [P1 state capacity results](docs/P1-STATE-CAPACITY-RESULTS.md)
- [P1 T2 repair results](docs/P1-T2-REPAIR-RESULTS.md)
- [P1 2D heterogeneous results](docs/P1-2D-HETEROGENEOUS-RESULTS.md)
- [P1 generalization results](docs/P1-GENERALIZATION-RESULTS.md)
- [Roadmap](ROADMAP.md)

## License

Apache-2.0.
