# COSMIC ORGANICS — processor readiness

## Direct assessment

“How close are we to a processor?” has three materially different answers:

| Target definition | Current engineering readiness |
|---|---:|
| **Specialized research processor / verifiable lattice accelerator** | **≈55–60%** |
| **Programmable FPGA demonstrator with a usable host interface** | **≈35–40%** |
| **General-purpose programmable processor** | **≈20–25%** |
| **Commercial processor product / production silicon** | **≈8–12%** |

These percentages are engineering heuristics over completed milestones, not benchmark scores, probability forecasts, or investment valuations.

The project is already beyond a conceptual diagram: it has an executable software kernel, synthesizable 64-PE RTL, deterministic proof machinery, strong controls, and a real physical capacity result. It is not yet a board-running processor with an ISA/compiler/runtime and measured power/timing.

## Readiness by layer

| Layer | Estimate | Evidence already present | Main missing boundary |
|---|---:|---|---|
| Scientific architecture and falsifiable model | **≈85%** | explicit state/transition model; strong controls; negative results retained | broader workloads, independent review, stable architecture specification |
| Software research kernel | **≈90%** | dense/sparse equality; deterministic replay; committed causal proofs; demo | stable public API, profiling suite, packaging polish, larger application set |
| Synthesizable specialized RTL | **≈75%** | 64 PEs; sparse scheduler; receipts; SHA; Merkle; HMAC | stable top-level profile contract, formal properties, resource-sharing optimization |
| Fit/routability of a useful FPGA profile | **≈35%** | complete full-profile capacity result on ECP5-85F | select a fit profile, route it, generate a bitstream, close timing |
| Physical board prototype | **0%** | no board run claimed | board selection, pins/clock/reset, programming, hardware-in-loop test |
| ISA/compiler/runtime programmability | **≈15%** | local transition law and workload adapters exist | instruction/config format, compiler or graph mapper, loader, host API, debug model |
| Production verification and security | **≈20–30%** | deterministic tests, frozen KATs, mutation rejection | formal verification, CDC/reset analysis, fault model, key provisioning, side-channel work |
| Commercial processor product | **≈8–12%** | differentiated research thesis and demonstrable stack | target customer, product workload, unit economics, board/software ecosystem, manufacturing |

## What already qualifies as “processor-like”

A processing architecture needs a state representation, execution elements, data/control movement, an execution rule, observable results, and a way to run repeatable workloads. COSMIC already has:

1. **Processing elements:** a 64-node A/M/C lattice in synthesizable RTL.
2. **Execution semantics:** synchronous local transitions with exact dense-reference behavior.
3. **Work activation:** a strong sparse dirty-frontier scheduler.
4. **State and interconnect:** local lattice state plus neighbor-dependent transitions.
5. **Result observability:** deterministic transition receipts.
6. **Integrity layer:** SHA commitments, Merkle inclusion paths, and HMAC root authentication.
7. **Reproducible workload:** a localized incident-map application demo.
8. **Physical feasibility discipline:** a fixed-device place-and-route capacity experiment rather than an inferred claim.

That is enough to call the work a **research processor architecture** or **specialized accelerator prototype in RTL**. It is not enough to call it a finished CPU or a market-ready chip.

## The central bottleneck discovered by HW-13

The full proof-heavy profile does not fit the selected ECP5-85F:

- combinational demand is about **39% over** device capacity;
- multiplier demand is about **28% over** device capacity;
- no frozen seed reached routing, so no Fmax exists for this profile/device pair.

The problem is no longer “can we describe the processor?” The next problem is **profile architecture and resource allocation**.

A sensible product architecture should not force every deployment to instantiate the entire proof stack on-core.

## Recommended hardware profiles

### 1. `CORE-LITE`

On-chip:

- 64-PE sparse A/M/C lattice;
- dirty-frontier scheduler;
- deterministic transition receipts;
- compact host stream.

Off-chip or deferred:

- SHA/Merkle/HMAC.

Purpose: obtain the first routed bitstream, board execution, and physical sparse-work measurements with the smallest semantic compromise.

### 2. `PROOF-EDGE`

On-chip:

- `CORE-LITE`;
- one shared SHA commitment engine;
- finite receipt batching;
- root/commitment export.

Off-chip:

- Merkle tree construction, inclusion-path storage, HMAC/signature service.

Purpose: keep tamper-evident commitments close to execution while moving bulk proof construction away from the critical resource budget.

### 3. `FULL-PROOF`

On-chip:

- current end-to-end receipt + SHA + Merkle + inclusion + HMAC profile.

Target:

- a larger FPGA or a resource-shared/serialized redesign.

Purpose: maximum autonomous proof generation, not minimum area.

## Critical path to a board-running processor

### Milestone A — release consolidation

- one documented release branch;
- one command for software verification;
- one application demo;
- one evidence matrix;
- CI on Python 3.11/3.12 plus RTL smoke.

### Milestone B — profile-fit frontier

Freeze and compare `CORE-LITE`, `PROOF-EDGE`, and a resource-shared `FULL-PROOF` candidate on one target. Do not change device or thresholds after seeing the result.

Success criterion: at least one meaningful profile fits, routes, packs, and meets a preregistered clock target across fixed seeds.

### Milestone C — hardware-in-loop board demo

- program an actual board;
- inject deterministic workloads;
- compare board outputs with the Python oracle;
- verify receipt/proof stream where applicable;
- report real clock and failure behavior.

### Milestone D — physical efficiency measurement

- wall-clock throughput;
- latency per logical tick and transition;
- board power at idle and under workload;
- joules per accepted transition;
- comparison against a CPU implementation for the same frozen workload.

Only here may energy or physical-performance claims begin.

### Milestone E — programmability layer

- stable configuration/ISA or graph format;
- compiler/mapper from workload graph to lattice configuration;
- host transport such as UART first, then AXI/PCIe if justified;
- runtime, tracing, reset/recovery, and debug protocol;
- versioned workload contract.

### Milestone F — product boundary

Choose one buyer problem where sparse local updates plus verifiable history are materially useful, for example:

- event-driven safety monitors;
- industrial/robotic local-state controllers;
- agent-action audit accelerators;
- high-integrity workflow/event processors;
- edge systems that need compact deterministic evidence.

A customer problem should select the final processor profile; the research stack should not dictate unnecessary hardware.

## Next decision

The next experiment should **not** be “add another cryptographic feature.” It should be:

> Which smallest profile preserves the differentiated COSMIC value, fits a frozen FPGA target, and produces the first real bitstream?

Recommended order:

1. finish the reproducible research release;
2. freeze the three profile boundaries;
3. synthesize and route them against the same target and fixed seeds;
4. select the cheapest profile that preserves sparse execution and a defensible evidence boundary;
5. move that exact profile to a physical board.

## Honest conclusion

COSMIC is close to a **real specialized research processor** and still far from a **commercial general-purpose processor**.

The hardest conceptual question — whether there is a coherent, testable computing architecture — has largely been answered positively. The next hard questions are ordinary but unforgiving engineering: fit, routing, host integration, board execution, power, programmability, and product-market focus.
