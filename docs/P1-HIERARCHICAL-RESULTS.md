# P1 — MORPHOS-S2 Hierarchical Scale Results

## Question

Can a second interaction scale recover some of the error-correction lost by MORPHOS-S1 without retuning parameters separately for 5×5, 7×7, and 9×9?

## Mechanism

S2 keeps the frozen S1 law:

```text
k_s1(L) = k0 * (5 / L)^0.25
```

and adds fixed 3×3 local domains. Same-domain nearest-neighbor contributions receive one extra scale factor:

```text
h(L) = (L / 5)^beta
```

Cross-domain edges remain at S1 strength.

At 5×5, `h(5) = 1`, so S2 is exactly S1.

## Discovery

The declared discovery grid is:

```text
beta = 0.00, 0.01, ..., 0.10
```

Selection does not optimize recovery directly. It chooses the **maximum** `beta` that keeps both of these true on every discovery corpus:

1. sampled binary-capacity delta versus majority CA is strictly positive;
2. seed-transition-cost ratio versus majority CA is below one.

Result:

```text
beta = 0.06  PASS
beta = 0.07  FAIL
```

At `beta = 0.06`:

- minimum discovery capacity delta: `+0.271302021817 bits`;
- mean discovery capacity delta: `+0.688199183844 bits`;
- maximum seed-transition-cost ratio: `0.413590604027×`.

The candidate is frozen before confirmation.

## Frozen confirmation

Nine fresh SHA-256 corpora are used: three each at 5×5, 7×7, and 9×9.

Across all nine:

- mean sampled capacity delta vs majority CA: `+0.468885075994 bits`;
- mean one-bit recovery delta vs majority CA: `-24.9353 pp`;
- mean recovery gain vs S1: `+3.1421 pp`;
- mean seed-transition-cost ratio vs majority CA: `0.277348252940×`;
- mean recovery-transition-cost ratio vs majority CA: `0.044979029641×`.

For the six larger-grid corpora only:

- S2 keeps a positive capacity delta on all six;
- S2 improves recovery over S1 on all six;
- mean recovery gain over S1: `+4.7132 pp`;
- minimum recovery gain over S1: `+0.2083 pp`;
- minimum capacity delta vs majority CA: `+0.289506617195 bits`.

## New negative evidence

One of the three fresh 5×5 confirmation corpora has a non-positive capacity delta versus majority CA.

Critically, S2 and S1 are identical at 5×5, and **both fail on that same corpus**.

Therefore the earlier S1 nine-corpus PASS must not be promoted into a universal claim that the capacity advantage is robust across arbitrary unseen 5×5 samples.

This is new falsification evidence, not a regression to hide.

## Gates

```text
large-scale capacity (7×7 / 9×9)          PASS
large-scale recovery gain vs S1           PASS
recovery parity vs majority CA             FAIL
fresh 5×5 capacity robustness              FAIL
full hierarchical generalization           FAIL
```

## Interpretation

S2 shows that a second spatial interaction scale can move the capacity/recovery Pareto point in the intended direction on larger lattices.

It does **not** close the generalization problem.

The remaining evidence points to two separate frontiers:

1. recovery still trails majority CA substantially at larger scale;
2. sampled capacity advantage itself is not yet robust enough across unseen 5×5 corpora.

The next experiment should therefore stop treating "capacity PASS" as a settled property. It should measure attractor/codebook robustness across a much broader frozen corpus and explicitly analyze distance between attractors before adding more repair pressure.

## Reproducibility

```bash
python -m benchmarks.run_hierarchical
python -m benchmarks.render_hierarchical_summary
```

Evidence identities:

```text
full result digest
f41a4e73ce88041a2608a27dab4207e913f297bd1dbc0acc875fa9662e140a3b

committed summary evidence digest
c9bb235ffe224a7bd7beae9f62e12b60b6ebe3be55828cdf808175f3eca07e62
```

The full report is regenerated in CI. The committed compact summary binds the full-result digest, discovery boundary, and scientific gate summary and is compared byte-for-byte.
