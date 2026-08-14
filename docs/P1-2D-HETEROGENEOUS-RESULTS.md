# P1 2D Heterogeneous Results

**Status:** exploratory candidate + frozen confirmation / new Pareto point, no full dominance

This experiment moves MORPHOS from a one-dimensional homogeneous rule into a 5×5 four-neighbor lattice with two cell classes arranged in a fixed checkerboard substrate.

The heterogeneous candidate uses anchor cells (threshold `0.5`, coupling `0.75`) and adaptive cells (threshold `0.35`, coupling `0.5`), with mixed-state relaxation threshold `0.05` and memory decay `0.0`. These values are algorithmic hypotheses, not calibrated material properties.

## Selection discipline

The candidate was selected during exploratory structured-pattern work and frozen before the confirmation corpus was evaluated. The result therefore separates a structured discovery suite of five declared geometric patterns from a confirmation suite of 256 previously unused binary 5×5 inputs generated deterministically from SHA-256 indexed bits with seed `2026081402`.

The confirmation result is the stronger evidence. The discovery result is not treated as an independent confirmatory test.

## Structured discovery result

| model | stable patterns | one-bit recovery | avg recovery transitions |
|---|---:|---:|---:|
| majority CA | 3 | 68.00% | 3.4533 |
| heterogeneous checkerboard | 3 | **73.33%** | **2.2133** |
| homogeneous anchor | 3 | 68.00% | 2.8000 |
| homogeneous adaptive | 4 | 51.00% | 1.7600 |

The discovery suite contains a local advantage over majority CA, but it was part of candidate selection and must not be used alone as evidence of general superiority.

## Frozen confirmation result

| model | binary fixed attractors | capacity bits | binary seed coverage | one-bit recovery | recovery cost | seed cost |
|---|---:|---:|---:|---:|---:|---:|
| majority CA | 147 | 7.1997 | 89.06% | **65.90%** | 38.8052 | 41.0742 |
| heterogeneous checkerboard | **200** | **7.6439** | 88.28% | 58.80% | **2.4586** | **15.2461** |
| homogeneous anchor | 90 | 6.4919 | 68.75% | 73.51% | 3.1502 | 23.4219 |
| homogeneous adaptive | 217 | 7.7616 | 89.84% | 47.71% | 1.8811 | 12.0430 |

Relative to majority CA, the heterogeneous candidate gains `0.4442` binary capacity bits, loses `7.10` percentage points of one-bit recovery, is within `0.78` percentage points of binary seed coverage, uses only `6.34%` of the majority CA recovery transition cost, and uses `37.12%` of its seed relaxation transition cost.

## What heterogeneity actually changed

The heterogeneous candidate is not dominated by any of the three declared comparison models across binary capacity, recovery, coverage, and recovery cost. However, it does **not** dominate them either. Homogeneous anchor has stronger recovery but lower capacity; homogeneous adaptive has greater capacity and lower cost but much weaker recovery; majority CA has stronger recovery and slightly higher coverage, but far higher transition cost and lower binary attractor capacity.

The result is therefore a **new Pareto point**, not a win.

The candidate also creates `24` mixed-state fixed attractors in the confirmation run. Those are reported separately and excluded from the binary-capacity comparison, so the extra `M` alphabet cannot silently inflate the binary memory claim.

## Interpretation

This is the first P1 result where changing geometry and cell heterogeneity produces a reproducible tradeoff that survives a frozen confirmation corpus rather than only a task-matched toy example.

It is still insufficient for a claim of computational superiority. The next test should challenge the Pareto point with larger lattices, multiple confirmation seeds, perturbations beyond one-bit flips, topology/mask ablations, recurrent/reservoir-style baselines, and eventually a physical-device cost model instead of raw transition counts.

Result digest: `47b0b631df4f47450c1530638e3ebe17dc3d7da2872aeeefe3e4c2b7b9fc9d3a`.
