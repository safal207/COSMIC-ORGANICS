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
├── MORPHOS-S1             fixed scale-aware coupling experiment
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
python -m benchmarks.run_scale_aware
```

The evidence chain intentionally preserves negative results: the first temporal failure, narrow robustness, external-baseline ties, the T1 mixed-state dead zone, T2's capacity/recovery/cost tradeoff, failure of frozen 5×5 constants to scale, and the new S1 recovery tradeoff.

The frozen 5×5 checkerboard candidate previously produced a reproducible new Pareto point versus majority CA. The Generalization Gate then showed that the same constants do **not** preserve the observed capacity advantage at 7×7 and 9×9.

MORPHOS-S1 tests one scale-aware law rather than per-size retuning:

```text
k_eff(L) = k0 * (5 / L)^0.25
```

`alpha = 0.25` is the minimum exponent that passes a declared nine-corpus discovery gate. It is frozen before nine new confirmation corpora.

Current S1 result:

- the frozen non-scale-aware candidate has `5 / 9` non-positive capacity-delta confirmation corpora;
- MORPHOS-S1 has `0 / 9` capacity failures;
- mean observed capacity delta is `+0.7288 bits`;
- mean seed-transition cost is `0.2684×` majority CA;
- mean one-bit recovery delta is `-31.24 pp`;
- mean recovery-transition cost is `0.0506×` majority CA.

Therefore **scale-capacity passes, recovery fails, and full scale generalization remains open**. S1 is a targeted repair of one generalization failure, not scale-general superiority.

Earlier full result artifacts remain under `results/`; the Generalization Gate uses its digest-bound summary, and S1 commits the complete deterministic `p1-scale-aware-v0.1.json` result. CI regenerates each declared evidence surface and compares it byte-for-byte.

## Research question

Can useful computation be expressed as controlled transitions of structured, mixed, and amorphous states, such that the computational state is also a persistent physical-like structure?

The software model is only the first test of that question.

## Documents

- [Vision](docs/VISION.md)
- [MORPHOS Protocol v0.1](docs/MORPHOS-PROTOCOL.md)
- [Scientific boundaries](docs/SCIENTIFIC-BOUNDARIES.md)
- [State algebra](spec/state-algebra.md)
- [MORPHOS cell](spec/morphos-cell.md)
- [MORPHOS-S1 scale-aware coupling](spec/scale-aware-coupling.md)
- [Evidence map](research/evidence-map.md)
- [P1 baseline results](docs/P1-BASELINE-RESULTS.md)
- [P1 temporal results](docs/P1-TEMPORAL-RESULTS.md)
- [P1 robustness results](docs/P1-ROBUSTNESS-RESULTS.md)
- [P1 external baseline results](docs/P1-EXTERNAL-BASELINE-RESULTS.md)
- [P1 state capacity results](docs/P1-STATE-CAPACITY-RESULTS.md)
- [P1 T2 repair results](docs/P1-T2-REPAIR-RESULTS.md)
- [P1 2D heterogeneous results](docs/P1-2D-HETEROGENEOUS-RESULTS.md)
- [P1 generalization results](docs/P1-GENERALIZATION-RESULTS.md)
- [P1 scale-aware results](docs/P1-SCALE-AWARE-RESULTS.md)
- [Roadmap](ROADMAP.md)

## License

Apache-2.0.
