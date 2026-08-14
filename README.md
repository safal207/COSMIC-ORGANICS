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
├── State Algebra          composition / interaction / delta / ratio
├── Evidence Map           claim -> source -> status
└── Research Horizon       materials -> physical neuro-systems -> biointerfaces
```

## MORPHOS-0

MORPHOS-0 models a one-dimensional lattice of cells with three coarse structural states:

- `A` — amorphous
- `M` — mixed / intermediate
- `C` — crystalline / ordered

An external stimulus and local coupling can cause a cell to move one state at a time. Updates are synchronous and deterministic.

```bash
python -m morphos.simulator
python -m unittest discover -s tests -v
```

MORPHOS-0 is deliberately small. Its purpose is to make the project falsifiable and testable before adding neural learning, richer physics, photonics, ionic systems, or biological interfaces.

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
- [Roadmap](ROADMAP.md)

## License

Apache-2.0.
