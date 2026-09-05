# COSMIC ORGANICS / MORPHOS

**Sparse transition-state execution with separately checkable evidence — a research processor stack.**

The software model computes the active frontier and records transitions. Execution owns state evolution; proof and authentication logic observe that evolution rather than decide the next state.

## Start here

| Your goal | Entry point |
|---|---|
| Start in Russian / начать по-русски | [START_HERE.md](START_HERE.md) |
| Run the existing software model and demo | Commands below |
| Find exact research sources and limits | [RESEARCH_INDEX.md](RESEARCH_INDEX.md) |
| Inspect readiness | [PROJECT_STATUS.json](PROJECT_STATUS.json) |
| Preserve experiments and manage branches | [REPOSITORY_GUIDE.md](REPOSITORY_GUIDE.md) |
| Read the complete previous technical introduction | [README.previous.md](README.previous.md) |

## What can be used today

| Track | Use | Boundary |
|---|---|---|
| Main software research kernel | Reproduce deterministic sparse/dense comparisons and proofs | Local workload evidence, not universal CPU superiority |
| Verified incident-map demo | Inspect one complete software use case | Deliberately localized service-map workload |
| RTL and frozen FPGA research profiles | Reproduce the named profile with its prescribed toolchain | Simulation, fit and physical-board evidence are separate |
| HW-22 held-flush experiment | Inspect a pinned latency intervention in a separate draft | Simulation-only; not on main, not a board or CPU-parity result |

## Run the software reference

Declared requirements: Python 3.11 or 3.12. From a repository checkout:

```sh
python -m venv .venv
# Activate .venv for your shell.
python -m pip install -e .
make verify
make demo
```

Without Make, use the exact commands in [README.previous.md](README.previous.md). Optional `make rtl-smoke` requires Icarus Verilog. Full FPGA place-and-route is intentionally outside the default software path.

Baseline main source: `6cca90a5fc9f3e98cde2906c65383bae0a6f7ef6`. This documentation pass did not rerun its tests or any hardware experiments and changes no runtime code.

## Research evidence and limitations

Start with [research status](docs/RESEARCH-STATUS.md), then the [selected-track index](RESEARCH_INDEX.md). Read milestone-specific statements at their exact revisions; older readiness pages are not proof that newer drafts have shipped.

Retain negative results: the full proof-heavy HW-12 profile did not fit its selected ECP5-85F target; Bardo-labelled mechanisms did not beat equally expressive strong conventional controls in the recorded comparisons. A narrower later profile must keep its own result and provenance, not overwrite those observations.

## Architecture family

[BardoCompute](https://github.com/safal207/BardoCompute): transition representation · [COSMIC-ORGANICS](https://github.com/safal207/COSMIC-ORGANICS): sparse execution · [ATMAN-LATTICE](https://github.com/safal207/ATMAN-LATTICE): authority and governed revision · [CaPU](https://github.com/safal207/CaPU): effect admission and recovery.

This is a map of intended roles, not a verified integrated system. The CaPU × ATMAN laboratories do not include COSMIC.

## Status, history and license

Readiness snapshot: **2026-09-05**. Production silicon, general-purpose CPU replacement, measured system-level speed/energy advantage and deployment safety are not established by these entry tracks.

Existing source paths, workflows, results, branches and Apache-2.0 [license](LICENSE) remain unchanged. The original README is preserved byte-for-byte at [README.previous.md](README.previous.md).
