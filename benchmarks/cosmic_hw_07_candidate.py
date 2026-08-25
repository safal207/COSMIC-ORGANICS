from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from benchmarks.cosmic_hw_06_vectors import build_sequences as build_phase1_sequences
from benchmarks.cosmic_hw_07_stress import (
    READY_PATTERNS,
    build_stress_sequences,
    validate_stress_corpus,
)
from morphos.grid2d import Grid2D, Grid2DConfig
from morphos.sparse_scheduler import DirtyNodeGrid2D

BENCHMARK_ID = "COSMIC-HW-07-CANDIDATE"
PROTOCOL = "COSMIC-HW-07/v0.1"
CELLS = 64
TICKS_PER_SEQUENCE = 12
PHASE_CODE = {"A": 0, "M": 1, "C": 2}
SYSTEM_TOPS = {
    "dense": "cosmic_hw06_dense_mesh64",
    "sparse": "cosmic_hw06_sparse_mesh64",
    "dense_receipt": "cosmic_hw07_dense_receipt_mesh64",
    "sparse_receipt": "cosmic_hw07_sparse_receipt_mesh64",
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
    value = 0
    for site, phase in enumerate(state):
        value |= PHASE_CODE[phase] << (2 * site)
    return value


def stimulus_bits(stimulus_s100: tuple[int, ...]) -> int:
    value = 0
    for site, stimulus in enumerate(stimulus_s100):
        value |= (stimulus & 0xFF) << (8 * site)
    return value


def pack_receipt(
    logical_tick: int,
    site: int,
    phase_before: str,
    phase_after: str,
    stimulus_s100: int,
    ordinal: int,
) -> int:
    return (
        ((logical_tick & 0xFFFF) << 24)
        | ((site & 0x3F) << 18)
        | ((PHASE_CODE[phase_before] & 0x3) << 16)
        | ((PHASE_CODE[phase_after] & 0x3) << 14)
        | ((stimulus_s100 & 0xFF) << 6)
        | (ordinal & 0x3F)
    )


def build_oracle() -> dict:
    config = Grid2DConfig(width=8, height=8, memory_decay=0.0)
    ticks: list[dict] = []
    receipts: list[int] = []
    sequences: list[dict] = []
    work = defaultdict(lambda: {"dense": 0, "sparse": 0, "transitions": 0})

    phase1 = list(build_phase1_sequences())
    stress = list(build_stress_sequences())
    all_sequences = []
    for vector in phase1:
        density_key = f"{vector.density:.2f}"
        group = {"0.01": 0, "0.05": 1, "0.20": 2, "1.00": 3}[density_key]
        all_sequences.append((vector, "always_ready", group, density_key, "phase1"))
    for vector in stress:
        all_sequences.append((vector, vector.ready_pattern, 4, "stress", "stress"))

    for sequence_index, (vector, ready_pattern, group, work_key, workload) in enumerate(all_sequences):
        if vector.initial_state != "A" * CELLS:
            raise RuntimeError("HW-07 RTL reset contract requires all-A sequence start")

        dense = Grid2D(vector.initial_state, config=config)
        sparse = DirtyNodeGrid2D(vector.initial_state, config=config)
        previous_s100 = [0] * CELLS
        receipt_start = len(receipts)

        for logical_tick, stimulus_s100 in enumerate(vector.stimuli_s100, start=1):
            scheduled = set(sparse._dirty_next)
            scheduled.update(
                site
                for site, (previous, current) in enumerate(zip(previous_s100, stimulus_s100))
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

            for ordinal, site in enumerate(changed_sites):
                receipts.append(
                    pack_receipt(
                        logical_tick,
                        site,
                        before[site],
                        after[site],
                        stimulus_s100[site],
                        ordinal,
                    )
                )

            ticks.append(
                {
                    "stimulus": stimulus_bits(stimulus_s100),
                    "state": state_bits(after),
                    "active": active_mask,
                    "changed": changed_mask,
                    "dirty": dirty_mask,
                }
            )
            work[work_key]["dense"] += CELLS
            work[work_key]["sparse"] += len(scheduled)
            work[work_key]["transitions"] += len(changed_sites)
            previous_s100 = list(stimulus_s100)

        sequences.append(
            {
                "sequence_index": sequence_index,
                "vector_id": vector.vector_id,
                "workload": workload,
                "ready_pattern": ready_pattern,
                "ready_pattern_id": READY_PATTERNS.index(ready_pattern),
                "group": group,
                "receipt_count": len(receipts) - receipt_start,
            }
        )

    assert len(sequences) == 320
    assert len(ticks) == 320 * TICKS_PER_SEQUENCE == 3840

    execution_work = {}
    for key, counts in sorted(work.items()):
        dense = counts["dense"]
        sparse = counts["sparse"]
        execution_work[key] = {
            "dense_pe_evaluations": dense,
            "sparse_pe_evaluations": sparse,
            "pe_evaluation_reduction": (dense - sparse) / dense,
            "committed_transitions": counts["transitions"],
        }

    return {
        "ticks": ticks,
        "receipts": receipts,
        "sequences": sequences,
        "execution_work": execution_work,
    }


def write_mem(path: Path, values, hex_digits: int) -> None:
    path.write_text(
        "".join(f"{int(value):0{hex_digits}x}\n" for value in values),
        encoding="utf-8",
    )


def make_testbench(oracle: dict, tmp: Path) -> str:
    ticks = oracle["ticks"]
    sequences = oracle["sequences"]
    receipts = oracle["receipts"]

    mem = {
        "stimulus": tmp / "stimulus.mem",
        "state": tmp / "state.mem",
        "active": tmp / "active.mem",
        "changed": tmp / "changed.mem",
        "dirty": tmp / "dirty.mem",
        "pattern": tmp / "pattern.mem",
        "group": tmp / "group.mem",
        "seq_receipts": tmp / "seq_receipts.mem",
        "receipts": tmp / "receipts.mem",
    }
    write_mem(mem["stimulus"], [row["stimulus"] for row in ticks], 128)
    write_mem(mem["state"], [row["state"] for row in ticks], 32)
    write_mem(mem["active"], [row["active"] for row in ticks], 16)
    write_mem(mem["changed"], [row["changed"] for row in ticks], 16)
    write_mem(mem["dirty"], [row["dirty"] for row in ticks], 16)
    write_mem(mem["pattern"], [row["ready_pattern_id"] for row in sequences], 1)
    write_mem(mem["group"], [row["group"] for row in sequences], 1)
    write_mem(mem["seq_receipts"], [row["receipt_count"] for row in sequences], 4)
    write_mem(mem["receipts"], receipts, 10)

    return f"""`timescale 1ns/1ps
module cosmic_hw07_tb;
    localparam integer TOTAL_SEQUENCES = 320;
    localparam integer TICKS_PER_SEQUENCE = 12;
    localparam integer TOTAL_TICKS = 3840;
    localparam integer TOTAL_RECEIPTS = {len(receipts)};

    reg clk=0;
    reg reset=1;
    reg tick_valid=0;
    reg [511:0] stimulus_bus=0;
    reg receipt_ready=1;

    wire control_tick_en;

    wire [127:0] d_phase, s_phase, dr_phase, sr_phase;
    wire [63:0] d_active, s_active, dr_active, sr_active;
    wire [63:0] d_changed, s_changed, dr_changed, sr_changed;
    wire [63:0] d_dirty, s_dirty, dr_dirty, sr_dirty;

    wire dr_tick_ready, sr_tick_ready;
    wire dr_rvalid, sr_rvalid;
    wire [39:0] dr_rdata, sr_rdata;
    wire [2:0] dr_occ, sr_occ;
    wire dr_pending, sr_pending;
    wire dr_enq, sr_enq, dr_deq, sr_deq;

    reg [511:0] stim_mem [0:TOTAL_TICKS-1];
    reg [127:0] state_mem [0:TOTAL_TICKS-1];
    reg [63:0] active_mem [0:TOTAL_TICKS-1];
    reg [63:0] changed_mem [0:TOTAL_TICKS-1];
    reg [63:0] dirty_mem [0:TOTAL_TICKS-1];
    reg [1:0] pattern_mem [0:TOTAL_SEQUENCES-1];
    reg [2:0] group_mem [0:TOTAL_SEQUENCES-1];
    reg [15:0] seq_receipt_mem [0:TOTAL_SEQUENCES-1];
    reg [39:0] receipt_mem [0:TOTAL_RECEIPTS-1];

    integer seq;
    integer local_tick;
    integer tick_index;
    integer physical_cycle;
    integer ready_before;
    integer receipts_seen=0;
    integer seq_receipts_seen=0;
    integer accepted_ticks=0;
    integer checks=0;
    integer enqueue_count=0;
    integer dequeue_count=0;
    integer serializer_active_cycles=0;
    integer physical_cycles_total=0;
    integer stalls_g0=0, stalls_g1=0, stalls_g2=0, stalls_g3=0, stalls_g4=0;
    integer max_occ_g0=0, max_occ_g1=0, max_occ_g2=0, max_occ_g3=0, max_occ_g4=0;
    integer watchdog;

    always #5 clk = ~clk;
    assign control_tick_en = tick_valid && dr_tick_ready && sr_tick_ready;

    cosmic_hw06_dense_mesh64 D(
        .clk(clk),.reset(reset),.tick_en(control_tick_en),.stimulus_bus(stimulus_bus),
        .phase_bus(d_phase),.active_mask(d_active),.changed_mask(d_changed),.dirty_mask(d_dirty));
    cosmic_hw06_sparse_mesh64 S(
        .clk(clk),.reset(reset),.tick_en(control_tick_en),.stimulus_bus(stimulus_bus),
        .phase_bus(s_phase),.active_mask(s_active),.changed_mask(s_changed),.dirty_mask(s_dirty));
    cosmic_hw07_dense_receipt_mesh64 DR(
        .clk(clk),.reset(reset),.tick_valid(tick_valid),.tick_ready(dr_tick_ready),.stimulus_bus(stimulus_bus),
        .phase_bus(dr_phase),.active_mask(dr_active),.changed_mask(dr_changed),.dirty_mask(dr_dirty),
        .receipt_valid(dr_rvalid),.receipt_ready(receipt_ready),.receipt_data(dr_rdata),
        .batch_occupancy(dr_occ),.pending_observation(dr_pending),
        .batch_enqueue_pulse(dr_enq),.batch_dequeue_pulse(dr_deq));
    cosmic_hw07_sparse_receipt_mesh64 SR(
        .clk(clk),.reset(reset),.tick_valid(tick_valid),.tick_ready(sr_tick_ready),.stimulus_bus(stimulus_bus),
        .phase_bus(sr_phase),.active_mask(sr_active),.changed_mask(sr_changed),.dirty_mask(sr_dirty),
        .receipt_valid(sr_rvalid),.receipt_ready(receipt_ready),.receipt_data(sr_rdata),
        .batch_occupancy(sr_occ),.pending_observation(sr_pending),
        .batch_enqueue_pulse(sr_enq),.batch_dequeue_pulse(sr_deq));

    function ready_for_cycle;
        input [1:0] pattern;
        input integer cycle;
        begin
            case(pattern)
                2'd0: ready_for_cycle = 1'b1;
                2'd1: ready_for_cycle = ((cycle % 4) != 3);
                2'd2: ready_for_cycle = ((cycle % 2) == 0);
                2'd3: ready_for_cycle = ((cycle % 16) >= 8);
                default: ready_for_cycle = 1'b0;
            endcase
        end
    endfunction

    task note_stall;
        input [2:0] group;
        begin
            case(group)
                3'd0: stalls_g0=stalls_g0+1;
                3'd1: stalls_g1=stalls_g1+1;
                3'd2: stalls_g2=stalls_g2+1;
                3'd3: stalls_g3=stalls_g3+1;
                default: stalls_g4=stalls_g4+1;
            endcase
        end
    endtask

    task note_occ;
        input [2:0] group;
        input [2:0] occ;
        begin
            case(group)
                3'd0: if(occ>max_occ_g0) max_occ_g0=occ;
                3'd1: if(occ>max_occ_g1) max_occ_g1=occ;
                3'd2: if(occ>max_occ_g2) max_occ_g2=occ;
                3'd3: if(occ>max_occ_g3) max_occ_g3=occ;
                default: if(occ>max_occ_g4) max_occ_g4=occ;
            endcase
        end
    endtask

    // Receipt handshakes are checked on the value visible before the active edge.
    always @(posedge clk) begin
        if(!reset) begin
            if(dr_tick_ready !== sr_tick_ready) $fatal(1,"dense/sparse receipt tick_ready mismatch");
            if(dr_rvalid !== sr_rvalid) $fatal(1,"dense/sparse receipt valid mismatch");
            if(dr_occ !== sr_occ) $fatal(1,"dense/sparse receipt occupancy mismatch");
            if(dr_pending !== sr_pending) $fatal(1,"dense/sparse pending mismatch");
            if(dr_rvalid) serializer_active_cycles = serializer_active_cycles + 1;
            if(dr_rvalid && receipt_ready) begin
                if(receipts_seen >= TOTAL_RECEIPTS) $fatal(1,"phantom receipt beyond oracle");
                if(dr_rdata !== receipt_mem[receipts_seen])
                    $fatal(1,"dense receipt mismatch index=%0d got=%h exp=%h",receipts_seen,dr_rdata,receipt_mem[receipts_seen]);
                if(sr_rdata !== receipt_mem[receipts_seen])
                    $fatal(1,"sparse receipt mismatch index=%0d got=%h exp=%h",receipts_seen,sr_rdata,receipt_mem[receipts_seen]);
                receipts_seen = receipts_seen + 1;
                seq_receipts_seen = seq_receipts_seen + 1;
                checks = checks + 2;
            end
        end
    end

    // Queue event pulses and occupancy are sampled after the authoritative edge.
    always @(negedge clk) begin
        if(!reset) begin
            if(dr_enq !== sr_enq) $fatal(1,"enqueue pulse mismatch");
            if(dr_deq !== sr_deq) $fatal(1,"dequeue pulse mismatch");
            if(dr_enq) enqueue_count = enqueue_count + 1;
            if(dr_deq) dequeue_count = dequeue_count + 1;
            note_occ(group_mem[seq], dr_occ);
        end
    end

    task reset_models;
        begin
            tick_valid=0; stimulus_bus=0; receipt_ready=1; reset=1;
            repeat(2) @(posedge clk); #1;
            reset=0;
            seq_receipts_seen=0;
            physical_cycle=0;
        end
    endtask

    task drive_one_tick;
        input integer index;
        input [1:0] pattern;
        input [2:0] group;
        integer accepted;
        begin
            accepted=0;
            while(!accepted) begin
                stimulus_bus=stim_mem[index];
                tick_valid=1;
                receipt_ready=ready_for_cycle(pattern,physical_cycle);
                #1;
                if(dr_tick_ready !== sr_tick_ready) $fatal(1,"tick_ready mismatch before edge");
                ready_before=(dr_tick_ready && sr_tick_ready);
                if(!ready_before) note_stall(group);
                @(posedge clk); #1;
                physical_cycle=physical_cycle+1;
                physical_cycles_total=physical_cycles_total+1;
                if(ready_before) begin
                    accepted=1;
                    accepted_ticks=accepted_ticks+1;
                    if(d_phase!==state_mem[index] || dr_phase!==state_mem[index]) $fatal(1,"dense state mismatch tick=%0d",index);
                    if(s_phase!==state_mem[index] || sr_phase!==state_mem[index]) $fatal(1,"sparse state mismatch tick=%0d",index);
                    if(d_phase!==dr_phase || s_phase!==sr_phase || d_phase!==s_phase) $fatal(1,"receipt execution contamination tick=%0d",index);
                    if(d_active!==64'hffffffffffffffff || dr_active!==64'hffffffffffffffff) $fatal(1,"dense active mismatch tick=%0d",index);
                    if(s_active!==active_mem[index] || sr_active!==active_mem[index]) $fatal(1,"sparse active mismatch tick=%0d",index);
                    if(d_changed!==changed_mem[index] || s_changed!==changed_mem[index] || dr_changed!==changed_mem[index] || sr_changed!==changed_mem[index]) $fatal(1,"changed mask mismatch tick=%0d",index);
                    if(d_dirty!==64'b0 || dr_dirty!==64'b0) $fatal(1,"dense dirty mismatch tick=%0d",index);
                    if(s_dirty!==dirty_mem[index] || sr_dirty!==dirty_mem[index]) $fatal(1,"sparse dirty mismatch tick=%0d",index);
                    checks=checks+14;
                end
            end
        end
    endtask

    task drain_sequence;
        input [1:0] pattern;
        input [2:0] group;
        input integer expected_receipts;
        begin
            tick_valid=0;
            stimulus_bus=0;
            watchdog=0;
            while((seq_receipts_seen < expected_receipts) || dr_pending || sr_pending || (dr_occ != 0) || (sr_occ != 0)) begin
                receipt_ready=ready_for_cycle(pattern,physical_cycle);
                @(posedge clk); #1;
                physical_cycle=physical_cycle+1;
                physical_cycles_total=physical_cycles_total+1;
                watchdog=watchdog+1;
                if(watchdog>10000) $fatal(1,"receipt drain watchdog sequence=%0d",seq);
            end
            if(seq_receipts_seen != expected_receipts) $fatal(1,"missing/duplicate receipts sequence=%0d got=%0d exp=%0d",seq,seq_receipts_seen,expected_receipts);
            // One extra cycle lets the final dequeue pulse reach the negedge metric sampler.
            receipt_ready=ready_for_cycle(pattern,physical_cycle);
            @(posedge clk); #1;
            physical_cycle=physical_cycle+1;
            physical_cycles_total=physical_cycles_total+1;
            checks=checks+1;
        end
    endtask

    initial begin
        $readmemh("{mem['stimulus']}",stim_mem);
        $readmemh("{mem['state']}",state_mem);
        $readmemh("{mem['active']}",active_mem);
        $readmemh("{mem['changed']}",changed_mem);
        $readmemh("{mem['dirty']}",dirty_mem);
        $readmemh("{mem['pattern']}",pattern_mem);
        $readmemh("{mem['group']}",group_mem);
        $readmemh("{mem['seq_receipts']}",seq_receipt_mem);
        $readmemh("{mem['receipts']}",receipt_mem);

        for(seq=0; seq<TOTAL_SEQUENCES; seq=seq+1) begin
            reset_models();
            for(local_tick=0; local_tick<TICKS_PER_SEQUENCE; local_tick=local_tick+1) begin
                tick_index=seq*TICKS_PER_SEQUENCE+local_tick;
                drive_one_tick(tick_index,pattern_mem[seq],group_mem[seq]);
            end
            drain_sequence(pattern_mem[seq],group_mem[seq],seq_receipt_mem[seq]);
        end

        tick_valid=0; receipt_ready=1;
        if(receipts_seen != TOTAL_RECEIPTS) $fatal(1,"global missing receipts got=%0d exp=%0d",receipts_seen,TOTAL_RECEIPTS);
        if(enqueue_count != dequeue_count) $fatal(1,"batch queue write/read mismatch enq=%0d deq=%0d",enqueue_count,dequeue_count);

        $display("COSMIC_HW07_SIM PASS checks=%0d sequences=%0d ticks=%0d receipts=%0d enq=%0d deq=%0d serializer_active=%0d physical_cycles=%0d stalls_g0=%0d stalls_g1=%0d stalls_g2=%0d stalls_g3=%0d stalls_g4=%0d max_g0=%0d max_g1=%0d max_g2=%0d max_g3=%0d max_g4=%0d",
            checks,TOTAL_SEQUENCES,accepted_ticks,receipts_seen,enqueue_count,dequeue_count,
            serializer_active_cycles,physical_cycles_total,
            stalls_g0,stalls_g1,stalls_g2,stalls_g3,stalls_g4,
            max_occ_g0,max_occ_g1,max_occ_g2,max_occ_g3,max_occ_g4);
        $finish;
    end
endmodule
"""


def parse_sim(text: str) -> dict:
    pattern = re.compile(
        r"COSMIC_HW07_SIM PASS checks=(\d+) sequences=(\d+) ticks=(\d+) receipts=(\d+) "
        r"enq=(\d+) deq=(\d+) serializer_active=(\d+) physical_cycles=(\d+) "
        r"stalls_g0=(\d+) stalls_g1=(\d+) stalls_g2=(\d+) stalls_g3=(\d+) stalls_g4=(\d+) "
        r"max_g0=(\d+) max_g1=(\d+) max_g2=(\d+) max_g3=(\d+) max_g4=(\d+)"
    )
    match = pattern.search(text)
    if not match:
        raise ValueError("COSMIC-HW-07 PASS marker not found")
    values = list(map(int, match.groups()))
    return {
        "checks": values[0],
        "sequences": values[1],
        "accepted_ticks": values[2],
        "receipts_emitted": values[3],
        "batch_fifo_writes": values[4],
        "batch_fifo_reads": values[5],
        "serializer_active_cycles": values[6],
        "physical_cycles": values[7],
        "backpressure_stalls_by_group": {
            "0.01": values[8],
            "0.05": values[9],
            "0.20": values[10],
            "1.00": values[11],
            "stress": values[12],
        },
        "max_reserved_batch_occupancy_by_group": {
            "0.01": values[13],
            "0.05": values[14],
            "0.20": values[15],
            "1.00": values[16],
            "stress": values[17],
        },
    }


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


def synthesize(yosys: str, rtl06: Path, rtl07: Path, top: str, tmp: Path) -> dict:
    json_path = tmp / f"{top}.json"
    read = f"read_verilog -sv {rtl06} {rtl07}; hierarchy -check -top {top}; flatten; "
    run_cmd([
        yosys,
        "-q",
        "-p",
        read + f"synth_xilinx -family xc7 -top {top}; write_json {json_path}",
    ])
    row = cell_counts_from_json(json_path, top)
    depth_text = run_cmd([
        yosys,
        "-p",
        f"read_verilog -sv {rtl06} {rtl07}; hierarchy -check -top {top}; proc; memory_map; opt; flatten; opt; ltp -noff",
    ])
    row["logic_depth_proxy"] = parse_ltp(depth_text)
    return row


def pct_delta(new: int, old: int) -> float | None:
    return None if old == 0 else (new - old) / old


def run() -> dict:
    root = Path(__file__).resolve().parents[1]
    rtl06 = root / "rtl" / "cosmic_hw_06.v"
    rtl07 = root / "rtl" / "cosmic_hw_07_receipt.v"
    manifest = json.loads((root / "benchmarks" / "cosmic_hw_07_manifest.json").read_text())
    if manifest["experiment_id"] != PROTOCOL:
        raise RuntimeError("frozen HW-07 manifest mismatch")

    stress_summary = validate_stress_corpus()
    oracle = build_oracle()
    iverilog = require_tool("iverilog")
    vvp = require_tool("vvp")
    yosys = require_tool("yosys")

    with tempfile.TemporaryDirectory(prefix="cosmic-hw-07-") as temp_dir:
        tmp = Path(temp_dir)
        tb = tmp / "cosmic_hw07_tb.v"
        tb.write_text(make_testbench(oracle, tmp), encoding="utf-8")
        sim_bin = tmp / "sim.out"
        run_cmd([
            iverilog,
            "-g2012",
            "-s",
            "cosmic_hw07_tb",
            "-o",
            str(sim_bin),
            str(rtl06),
            str(rtl07),
            str(tb),
        ])
        simulation = parse_sim(run_cmd([vvp, str(sim_bin)]))
        synthesis = {
            key: synthesize(yosys, rtl06, rtl07, top, tmp)
            for key, top in SYSTEM_TOPS.items()
        }

    synthesis["dense"]["architectural_state_bits"] = 128
    synthesis["sparse"]["architectural_state_bits"] = 128
    synthesis["dense_receipt"]["architectural_state_bits"] = 128
    synthesis["sparse_receipt"]["architectural_state_bits"] = 128
    synthesis["dense"]["receipt_metadata_buffer_bits"] = 0
    synthesis["sparse"]["receipt_metadata_buffer_bits"] = 0
    # 4*848 batch snapshots + 657 pending snapshot/valid + 16 logical tick
    # + 13 queue pointers/count/ordinal + 2 exported event-pulse registers.
    declared_receipt_state_bits = 4080
    synthesis["dense_receipt"]["receipt_metadata_buffer_bits"] = declared_receipt_state_bits
    synthesis["sparse_receipt"]["receipt_metadata_buffer_bits"] = declared_receipt_state_bits

    deltas = {
        "dense_receipt_minus_dense": {
            metric: synthesis["dense_receipt"][metric] - synthesis["dense"][metric]
            for metric in ("lut", "ff", "bram", "lutram", "core_cells_excluding_io", "logic_depth_proxy")
        },
        "sparse_receipt_minus_sparse": {
            metric: synthesis["sparse_receipt"][metric] - synthesis["sparse"][metric]
            for metric in ("lut", "ff", "bram", "lutram", "core_cells_excluding_io", "logic_depth_proxy")
        },
        "sparse_receipt_minus_dense_receipt": {
            metric: synthesis["sparse_receipt"][metric] - synthesis["dense_receipt"][metric]
            for metric in ("lut", "ff", "bram", "lutram", "core_cells_excluding_io", "logic_depth_proxy")
        },
    }
    delta_fractions = {
        "dense_receipt_minus_dense": {
            metric: pct_delta(synthesis["dense_receipt"][metric], synthesis["dense"][metric])
            for metric in ("lut", "ff", "core_cells_excluding_io", "logic_depth_proxy")
        },
        "sparse_receipt_minus_sparse": {
            metric: pct_delta(synthesis["sparse_receipt"][metric], synthesis["sparse"][metric])
            for metric in ("lut", "ff", "core_cells_excluding_io", "logic_depth_proxy")
        },
    }

    execution_work = oracle["execution_work"]
    low_activity_gate = all(
        execution_work[key]["pe_evaluation_reduction"] >= 0.50
        for key in ("0.01", "0.05")
    )
    functional_gate = (
        simulation["sequences"] == 320
        and simulation["accepted_ticks"] == 3840
        and simulation["receipts_emitted"] == len(oracle["receipts"])
        and simulation["batch_fifo_writes"] == simulation["batch_fifo_reads"]
    )

    decision = (
        "SPARSE_PLUS_RECEIPT_PARETO_SUPPORTED"
        if functional_gate and low_activity_gate
        else "RECEIPT_SEMANTICS_NOT_PRESERVED"
    )

    return {
        "benchmark_id": BENCHMARK_ID,
        "protocol": PROTOCOL,
        "parent_hardware_head": manifest["parent_hardware_head"],
        "decision": decision,
        "functional_gate": functional_gate,
        "sparse_low_activity_gate": low_activity_gate,
        "simulation": simulation,
        "execution_work": execution_work,
        "receipt": {
            "width_bits": 40,
            "expected_receipts": len(oracle["receipts"]),
            "missing_receipts": 0,
            "duplicate_receipts": 0,
            "phantom_receipts": 0,
            "field_match_fraction": 1.0,
            "serialization_order": "ascending_site_id",
            "batch_fifo_depth": 4,
            "batch_snapshot_bits": 848,
            "declared_receipt_state_bits": declared_receipt_state_bits,
        },
        "stress": stress_summary,
        "synthesis": synthesis,
        "structural_deltas": deltas,
        "structural_delta_fractions": delta_fractions,
        "proof_logic_present": False,
        "cryptographic_commitment_generated_in_hw": False,
        "execution_semantic_contamination": 0,
        "synthetic_combined_score_used": False,
        "timing_decisive": False,
        "claim_boundary": (
            "Synthesizable transition-receipt observer RTL, Icarus functional simulation "
            "and Yosys Xilinx-7 structural mapping only. Backpressure and enabled-PE work "
            "are logical/control counts, not measured power. No SHA/Merkle accelerator, "
            "placed/routed Fmax, board energy, ASIC PPA or end-to-end proof claim."
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
