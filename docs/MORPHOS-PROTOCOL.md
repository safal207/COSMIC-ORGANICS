# MORPHOS Protocol v0.1

**Status:** HYPOTHESIS / computational specification

MORPHOS is a protocol for representing computation as controlled transition of a structured medium.

## 1. State

A material-like element is represented as:

\[
M_t = (q_t, e_t, h_t, p_t)
\]

where:

- `q_t` — coarse structural state;
- `e_t` — local energy or activation proxy;
- `h_t` — retained transition history / memory;
- `p_t` — optional measurable properties.

MORPHOS-0 uses `q in {A, M, C}`.

## 2. Environment

At time `t`, a cell receives:

\[
U_t = (I_t, N_t, C_t)
\]

where:

- `I_t` — external stimulus;
- `N_t` — neighborhood state;
- `C_t` — constraints and protocol parameters.

## 3. Transition

The general transition is:

\[
M_{t+1} = \Phi(M_t, U_t, \Delta t)
\]

For MORPHOS-0, a scalar drive is computed as:

\[
d_t = I_t + \lambda(\bar q_N - q_t)
\]

where `lambda` is local coupling and `q` is numerically embedded as `A=0`, `M=0.5`, `C=1`.

If `d_t` crosses the crystallization threshold, the state moves one step toward `C`. If it crosses the negative amorphization threshold, it moves one step toward `A`. Otherwise it is retained.

Updates are **synchronous**: all next states are computed from the same previous state.

## 4. Function

The protocol does not prescribe one definition of computational output. A function may be encoded in:

- final state;
- spatial pattern;
- order parameter;
- transition count;
- time to convergence;
- persistent response to a pulse sequence.

## 5. Evidence envelope

Every experiment should bind:

```text
protocol_version
initial_state
parameters
stimulus_sequence
final_state
metrics
state_digest
```

This makes a run independently reproducible at the software-model level.

## 6. Non-claims

MORPHOS-0 is not a validated physical simulation of a specific phase-change compound. Parameters are dimensionless and phenomenological. Physical mapping requires calibration against experimental data for a named material/device.
