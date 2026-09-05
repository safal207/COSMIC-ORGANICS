# COSMIC-ORGANICS — research index

Snapshot: 2026-09-05. [Start](README.md) · [Lifecycle](REPOSITORY_GUIDE.md)

Selected entry tracks, not a complete branch audit. The main research stack was consolidated by PR #100; hardware draft branches retain their own source and evidence boundaries.

| Track | Exact source / evidence | Readiness |
|---|---|---|
| Main software kernel and incident-map demo | `6cca90a5fc9f3e98cde2906c65383bae0a6f7ef6`; [release PR #100](https://github.com/safal207/COSMIC-ORGANICS/pull/100) | Executable research reference, not production |
| Integrated sparse/proof kernel | [PR #69](https://github.com/safal207/COSMIC-ORGANICS/pull/69), [status](docs/RESEARCH-STATUS.md) | Frozen software workload observations |
| Full proof-heavy FPGA capacity boundary | [PR #97](https://github.com/safal207/COSMIC-ORGANICS/pull/97) and preserved [technical introduction](README.previous.md) | Negative fit result for that selected profile/device, not a universal impossibility |
| HW-22 held-flush intervention | `89d055284bdc745fb9d85a7661319287283f1600`; [draft PR #125](https://github.com/safal207/COSMIC-ORGANICS/pull/125) | `EARLY_HELD_FLUSH_CAUSAL_REDUCTION_SUPPORTED_SIMULATION_ONLY` |

## Exact-source worktrees

Main reference:

```sh
git fetch origin
git worktree add --detach ../COSMIC-reference 6cca90a5fc9f3e98cde2906c65383bae0a6f7ef6
cd ../COSMIC-reference
python -m venv .venv
# Activate .venv for your shell.
python -m pip install -e .
make verify
make demo
```

For HW-22, use a separate worktree at `89d055284bdc745fb9d85a7661319287283f1600` and the exact PR/source protocol, not main's quickstart as a substitute for its hardware verification.

## HW-22 lineage and limit

Parent: `a4446fc93cc4ab4fdf4dc56021e76f1c8e85b30b` on `feat/cosmic-hw-21-network-pyramid`. The draft targets that branch, not main, and adds five files. Inherited RTL is unchanged; the bounded comparison changes testbench flush policy.

Its recorded seven-engine comparison reduces 257 to 198 cycles. The converted time at inherited modeled 20.25 MHz is not a newly established physical frequency. Synthesis, place-and-route, board execution, Fmax, power and energy for HW-22 remain NOT_RUN. CPU parity and superiority are not claimed. This organization pass does not rerun or expand that evidence.

## Preserved history and promotion

Existing `research/`, `results/`, `release/`, `rtl/`, tests and branch names are retained. Documentation publication does not merge hardware drafts, change their PR targets or reclassify negative results. Before promotion, specify the selected source, dependencies, exact proposed tree, review and tests, and what remains outside main.

The next useful performance question is full-path cost on a declared real workload, including scheduling, I/O and evidence construction; do not replace it with a count of enabled nodes or SHA engines.
