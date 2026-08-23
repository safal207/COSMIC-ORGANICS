# COSMIC-HW-06 methodology

COSMIC-HW-06 is the first RTL-oriented boundary for the surviving COSMIC-ORGANICS mechanisms. It does not assume that a lattice representation, proof tag, or Bardo naming is intrinsically more efficient than a conventional design.

## Boundary

The first stage uses synthesizable Verilog/SystemVerilog, functional simulation, and Yosys structural Xilinx-7 mapping. It does not make placed/routed FPGA timing, board-power, energy, ASIC-PPA, novelty, or universal-superiority claims.

## Parent gate

The hardware candidate is downstream of COSMIC-KERNEL-05. The hardware preregistration may be frozen before the software candidate's custom hosted verdict is visible, but no RTL result may be credited as validated unless the parent software semantics are independently green.

## Equal-semantics systems

- DENSE_MESH_64: 8x8 A/M/C mesh, every PE evaluated per logical tick.
- SPARSE_MESH_64: same transition semantics with strong conventional dirty/frontier scheduling.
- DENSE_MESH_64_PROOF: dense execution plus observational transition receipts.
- SPARSE_MESH_64_PROOF: sparse execution plus the same observational transition receipts.

Proof logic observes committed transitions after the authoritative state update. It must not affect phase decisions, dirty-frontier membership, or transition count.

## Anti-strawman rule

Any generic optimization granted to a Cosmic-labelled design must also be granted to an equally expressive conventional control. This includes dirty scheduling, parent-set commitments, caches, multi-port memories, and composition primitives. A tie is a valid negative result.

## Primary questions

1. Does sparse RTL remain exactly equivalent to dense RTL on every frozen tick?
2. Does sparse RTL reduce PE evaluations by at least 50% at 1% and 5% activity?
3. What structural cost in LUT/FF/BRAM and cycle cost is paid for sparse scheduling?
4. What incremental cost is paid for proof generation?
5. Does sparse hardware converge toward or lose to dense at 100% activity?

Execution, synthesis, and proof cost are separate dimensions. There is no synthetic winner score.
