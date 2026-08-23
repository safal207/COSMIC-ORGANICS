from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from benchmarks.cosmic_hw_06_vectors import CELLS, build_sequences
from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.sparse_scheduler import DirtyNodeGrid2D

BENCHMARK_ID = "COSMIC-HW-06-PHASE1"
VERSION = "0.1"
PROTOCOL = "COSMIC-HW-06/v0.1 dense-sparse-64pe"
TOPS = {
    "dense": "cosmic_hw06_dense_mesh64",
    "sparse": "cosmic_hw06_sparse_mesh64",
}


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required tool not found: {name}")
    return path


def run_cmd(cmd: list[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc.stdout + proc.stderr


def mask_from_sites(sites) -> int:
    value = 0
    for site in sites:
        value |= 1 << site
    return value


def state_bits(state: str) -> int:
    encoding = {"A": 0, "M": 1, "C": 2}
    value = 0
    for site, phase in enumerate(state):
        value |= encoding[phase] << (2 * site)
    return value


def stimulus_bits(stimulus_s100: tuple[int, ...]) -> int:
    value = 0
    for site, stimulus in enumerate(stimulus_s100):
        value |= (stimulus & 0xFF) << (8 * site)
    return value


def build_expected() -> tuple[list[dict], dict]:
    config = Grid2DConfig(width=8, height=8, memory_decay=0.0)
    rows: list[dict] = []
    totals = defaultdict(lambda: {"dense": 0, "sparse": 0, "transitions": 0})

    for vector in build_sequences():
        dense = Grid2D(vector.initial_state, config=config)
        sparse = DirtyNodeGrid2D(vector.initial_state, config=config)
        previous_s100 = [0] * CELLS
        ticks = []

        for stimulus_s100 in vector.stimuli_s100:
            scheduled = set(sparse._dirty_next)
            scheduled.update(
                site
                for site, (previous, current) in enumerate(
                    zip(previous_s100, stimulus_s100)
                )
                if previous != current
            )
            active_mask = mask_from_sites(scheduled)
            before = dense.state_string()
            stimulus = [value / 100.0 for value in stimulus_s100]
            dense.step(stimulus)
            sparse.step(stimulus)
            after = dense.state_string()
            if sparse.state_string() != after:
                raise RuntimeError("frozen sparse software control diverged from dense")

            changed_sites = [
                site for site, (left, right) in enumerate(zip(before, after))
                if left != right
            ]
            changed_mask = mask_from_sites(changed_sites)
            dirty_mask = mask_from_sites(sparse._dirty_next)

            ticks.append(
                {
                    "stimulus": stimulus_bits(stimulus_s100),
                    "state": state_bits(after),
                    "active": active_mask,
                    "changed": changed_mask,
                    "dirty": dirty_mask,
                }
            )
            totals[vector.density]["dense"] += CELLS
            totals[vector.density]["sparse"] += len(scheduled)
            totals[vector.density]["transitions"] += len(changed_sites)
            previous_s100 = list(stimulus_s100)

        rows.append(
            {
                "vector_id": vector.vector_id,
                "density": vector.density,
                "ticks": ticks,
            }
        )

    summary = {}
    for density, counts in sorted(totals.items()):
        dense = counts["dense"]
        sparse = counts["sparse"]
        summary[f"{density:.2f}"] = {
            "dense_pe_evaluations": dense,
            "sparse_pe_evaluations": sparse,
            "pe_evaluation_reduction": (dense - sparse) / dense,
            "committed_transitions": counts["transitions"],
        }
    return rows, summary


def make_testbench(rows: list[dict]) -> str:
    body = [
        "`timescale 1ns/1ps",
        "module cosmic_hw06_phase1_tb;",
        "reg clk=0; reg reset=1; reg tick_en=0; reg [511:0] stimulus_bus=0;",
        "wire [127:0] dense_phase, sparse_phase;",
        "wire [63:0] dense_active, dense_changed, dense_dirty;",
        "wire [63:0] sparse_active, sparse_changed, sparse_dirty;",
        "integer checks=0; integer vectors=0; integer ticks=0;",
        "always #5 clk = ~clk;",
        "cosmic_hw06_dense_mesh64 D(.clk(clk),.reset(reset),.tick_en(tick_en),.stimulus_bus(stimulus_bus),.phase_bus(dense_phase),.active_mask(dense_active),.changed_mask(dense_changed),.dirty_mask(dense_dirty));",
        "cosmic_hw06_sparse_mesh64 S(.clk(clk),.reset(reset),.tick_en(tick_en),.stimulus_bus(stimulus_bus),.phase_bus(sparse_phase),.active_mask(sparse_active),.changed_mask(sparse_changed),.dirty_mask(sparse_dirty));",
        "task reset_models; begin reset=1; tick_en=0; stimulus_bus=0; repeat(2) @(posedge clk); #1; reset=0; if(dense_phase!==128'b0 || sparse_phase!==128'b0) $fatal(1,\"reset state mismatch\"); end endtask",
        "task drive_tick; input [511:0] stim; input [127:0] exp_state; input [63:0] exp_active; input [63:0] exp_changed; input [63:0] exp_dirty; begin",
        "stimulus_bus=stim; tick_en=1; @(posedge clk); #1; ticks=ticks+1;",
        "if(dense_phase!==exp_state) $fatal(1,\"dense state mismatch tick=%0d\",ticks); checks=checks+1;",
        "if(sparse_phase!==exp_state) $fatal(1,\"sparse state mismatch tick=%0d\",ticks); checks=checks+1;",
        "if(dense_phase!==sparse_phase) $fatal(1,\"dense/sparse divergence tick=%0d\",ticks); checks=checks+1;",
        "if(dense_active!==64'hffffffffffffffff) $fatal(1,\"dense active mismatch tick=%0d\",ticks); checks=checks+1;",
        "if(sparse_active!==exp_active) $fatal(1,\"sparse active mismatch tick=%0d got=%h exp=%h\",ticks,sparse_active,exp_active); checks=checks+1;",
        "if(dense_changed!==exp_changed) $fatal(1,\"dense changed mismatch tick=%0d\",ticks); checks=checks+1;",
        "if(sparse_changed!==exp_changed) $fatal(1,\"sparse changed mismatch tick=%0d\",ticks); checks=checks+1;",
        "if(sparse_dirty!==exp_dirty) $fatal(1,\"sparse dirty mismatch tick=%0d got=%h exp=%h\",ticks,sparse_dirty,exp_dirty); checks=checks+1;",
        "if(dense_dirty!==64'b0) $fatal(1,\"dense dirty must remain zero\"); checks=checks+1;",
        "end endtask",
        "initial begin",
    ]
    for row in rows:
        body.append("reset_models(); vectors=vectors+1;")
        for tick in row["ticks"]:
            body.append(
                "drive_tick(512'h{stimulus:0128x},128'h{state:032x},64'h{active:016x},64'h{changed:016x},64'h{dirty:016x});".format(
                    **tick
                )
            )
    body += [
        '$display("COSMIC_HW06_PHASE1_SIM PASS checks=%0d vectors=%0d ticks=%0d",checks,vectors,ticks);',
        "$finish; end",
        "endmodule",
    ]
    return "\n".join(body) + "\n"


def parse_sim(text: str) -> dict:
    match = re.search(
        r"COSMIC_HW06_PHASE1_SIM PASS checks=(\d+) vectors=(\d+) ticks=(\d+)",
        text,
    )
    if not match:
        raise ValueError("phase-1 PASS marker not found")
    checks, vectors, ticks = map(int, match.groups())
    return {"checks": checks, "vectors": vectors, "ticks": ticks}


def parse_ltp(text: str) -> int:
    matches = re.findall(r"length\s*=?\s*(\d+)", text, flags=re.IGNORECASE)
    if not matches:
        raise ValueError("Yosys ltp path length not found")
    return max(int(value) for value in matches)


def cell_counts_from_json(path: Path, top: str) -> dict:
    data = json.loads(path.read_text())
    module = data["modules"][top]
    counts = Counter(cell.get("type", "") for cell in module.get("cells", {}).values())
    lut = sum(value for key, value in counts.items() if re.fullmatch(r"LUT[1-6]", key))
    ff_types = {"FDRE", "FDSE", "FDCE", "FDPE"}
    ff = sum(value for key, value in counts.items() if key in ff_types)
    bram = sum(value for key, value in counts.items() if key.startswith("RAMB18") or key.startswith("RAMB36"))
    lutram = sum(value for key, value in counts.items() if key.startswith("RAM32") or key.startswith("RAM64") or key.startswith("RAM128"))
    io = sum(value for key, value in counts.items() if key in {"IBUF", "OBUF", "OBUFT", "IOBUF"})
    total = sum(counts.values())
    return {
        "total_mapped_cells": total,
        "core_cells_excluding_io": total - io,
        "lut": lut,
        "ff": ff,
        "bram": bram,
        "lutram": lutram,
        "cell_types": dict(sorted(counts.items())),
    }


def synthesize(yosys: str, rtl: Path, top: str, tmp: Path) -> dict:
    json_path = tmp / f"{top}.json"
    synth_script = (
        f"read_verilog -sv {rtl}; synth_xilinx -family xc7 -top {top}; "
        f"write_json {json_path}"
    )
    run_cmd([yosys, "-q", "-p", synth_script])
    row = cell_counts_from_json(json_path, top)
    depth_script = (
        f"read_verilog -sv {rtl}; hierarchy -check -top {top}; "
        "proc; memory_map; opt; flatten; opt; ltp -noff"
    )
    row["logic_depth_proxy"] = parse_ltp(run_cmd([yosys, "-p", depth_script]))
    return row


def tool_version(cmd: list[str]) -> str:
    text = run_cmd(cmd)
    return text.strip().splitlines()[0] if text.strip() else "unknown"


def run() -> dict:
    root = Path(__file__).resolve().parents[1]
    rtl = root / "rtl" / "cosmic_hw_06.v"
    iverilog = require_tool("iverilog")
    vvp = require_tool("vvp")
    yosys = require_tool("yosys")
    rows, work = build_expected()

    with tempfile.TemporaryDirectory(prefix="cosmic-hw-06-phase1-") as temp_dir:
        tmp = Path(temp_dir)
        tb = tmp / "cosmic_hw06_phase1_tb.v"
        tb.write_text(make_testbench(rows), encoding="utf-8")
        sim_bin = tmp / "sim.out"
        run_cmd([
            iverilog, "-g2012", "-s", "cosmic_hw06_phase1_tb",
            "-o", str(sim_bin), str(rtl), str(tb)
        ])
        simulation = parse_sim(run_cmd([vvp, str(sim_bin)]))
        synthesis = {
            key: synthesize(yosys, rtl, top, tmp)
            for key, top in TOPS.items()
        }

    synthesis["dense"]["architectural_state_bits"] = 128
    synthesis["dense"]["scheduler_metadata_bits"] = 0
    synthesis["sparse"]["architectural_state_bits"] = 128
    synthesis["sparse"]["scheduler_metadata_bits"] = 64 + 64 * 8

    low_density_gate = all(
        work[key]["pe_evaluation_reduction"] >= 0.50 for key in ("0.01", "0.05")
    )
    functional_gate = simulation["vectors"] == 256 and simulation["ticks"] == 256 * 12
    decision = (
        "SPARSE_RTL_VALUE_SUPPORTED"
        if low_density_gate and functional_gate
        else "SPARSE_RTL_VALUE_NOT_SUPPORTED"
    )

    return {
        "benchmark_id": BENCHMARK_ID,
        "version": VERSION,
        "protocol": PROTOCOL,
        "decision": decision,
        "tools": {
            "iverilog": tool_version([iverilog, "-V"]),
            "yosys": tool_version([yosys, "-V"]),
        },
        "simulation": simulation,
        "execution_work": work,
        "synthesis": synthesis,
        "proof_logic_present": False,
        "cycles_per_logical_tick_reference": 1,
        "timing_decisive": False,
        "no_synthetic_winner_score": True,
        "claim_boundary": (
            "Synthesizable 64-PE parallel reference RTL, Icarus functional simulation and "
            "Yosys Xilinx-7 structural mapping only. PE-evaluation reduction is an enable/work "
            "count, not measured board power. No post-route Fmax, joules/transition, thermal, "
            "ASIC PPA, CPU/GPU superiority or lattice-QCD equivalence claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = run()
    print(json.dumps(report, indent=2 if args.json else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
