# Verified Incident Map — application demo v0.1

This demo turns the frozen COSMIC-KERNEL-05 mechanisms into one small, reviewable application surface.

## Scenario

A `16 × 16` service map receives two localized incident signals and later two explicit remediation signals.

For this demo only, the abstract MORPHOS phases are labelled:

| Phase | Application label |
|---|---|
| `A` | nominal |
| `M` | elevated / transition |
| `C` | critical |

These labels are illustrative. The model is not calibrated against real operational-risk data.

## Compared systems

The exact same deterministic 24-tick workload is executed by:

1. **Dense reference** — evaluates every map cell every logical tick.
2. **Strong sparse control** — reevaluates only changed-stimulus cells and the exact dirty causal frontier.
3. **Sparse + committed proof** — the same sparse execution plus the frozen observational Merkle-bound causal-proof collector.

The proof path cannot change a transition or future scheduling. It observes only completed transitions.

## Required gates

The demo fails unless all of the following hold:

- dense and sparse states are equal after every tick;
- final states and transition counts are equal;
- transition replay reconstructs the final state;
- dense and sparse proof representations are byte-identical;
- both proofs verify independently;
- a mutated transition claim is rejected;
- every completed transition is audited;
- sparse node evaluations are at least 50% lower than dense evaluations on this deliberately localized workload.

The final point is an application-demo gate, not a new general benchmark claim. The stronger frozen scientific evidence remains COSMIC-KERNEL-05.

## Run

```bash
PYTHONPATH=. python demos/verified_incident_map.py
```

Focused verification:

```bash
python -m pip install pytest
PYTHONPATH=. python -m pytest -q tests/test_verified_incident_map.py
```

The script emits JSON containing:

- semantic equality and replay checks;
- proof verification and mutation-rejection checks;
- dense and sparse scheduler work counters;
- deterministic proof cost;
- a SHA-256 digest of the canonical proof payload.

## Why this demo matters

The research repository previously proved mechanisms but did not expose one easy application story. This demo shows the intended product shape more clearly:

```text
localized events
      ↓
strong sparse causal frontier
      ↓
state result
      +
independently checkable transition evidence
```

A practical future product would supply a domain-specific state model, event adapter, verifier service, and deployment target. Those layers are not implemented by this demo.

## Claim boundary

This demo does **not** establish:

- calibrated incident or risk prediction;
- a Bardo-specific efficiency advantage;
- measured energy savings;
- CPU/GPU superiority;
- FPGA timing or board execution;
- secure production key management;
- a universal processor architecture.

It establishes a reproducible software example of the already frozen sparse-execution and committed-proof mechanisms.
