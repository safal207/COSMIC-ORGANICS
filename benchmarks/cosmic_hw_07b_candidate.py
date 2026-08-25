from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from benchmarks.cosmic_hw_07_candidate import build_oracle, parse_ltp, write_mem
from benchmarks.cosmic_hw_07_stress import READY_PATTERNS, validate_stress_corpus

BENCHMARK_ID = "COSMIC-HW-07B-CANDIDATE"
PROTOCOL = "COSMIC-HW-07B/v0.1"

SYSTEMS = {
    "CONTROL_F4_FLAT": {
        "top": "cosmic_hw07_sparse_receipt_mesh64",
        "depth": 4,
        "selector": "flat_64_site_priority",
    },
    "CANDIDATE_F4_HIER": {
        "top": "cosmic_hw07b_sparse_f4_hier",
        "depth": 4,
        "selector": "hierarchical_8x8_priority",
    },
    "CANDIDATE_F2_HIER": {
        "top": "cosmic_hw07b_sparse_f2_hier",
        "depth": 2,
        "selector": "hierarchical_8x8_priority",
    },
    "CANDIDATE_F1_HIER": {
        "top": "cosmic_hw07b_sparse_f1_hier",
        "depth": 1,
        "selector": "hierarchical_8x8_priority",
    },
}

STALL_KEYS = ("0.01", "0.05", "0.20", "1.00", "stress")
PARETO_KEYS = (
    "lut",
    "ff",
    "core_cells_excluding_io",
    "logic_depth_proxy",
    "stall_0.01",
    "stall_0.05",
    "stall_0.20",
    "stall_1.00",
    "stall_stress",
)


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required tool not found: {name}")
    return path


def run_cmd(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc.stdout + proc.stderr


def prepare_memories(oracle: dict, tmp: Path) -> dict[str, Path]:
    ticks = oracle["ticks"]
    sequences = oracle["sequences"]
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
    write_mem(mem["receipts"], oracle["receipts"], 10)
    return mem


def make_testbench(top: str, oracle: dict, mem: dict[str, Path], tag: str) -> str:
    total_receipts = len(oracle["receipts"])
    return f"""`timescale 1ns/1ps
module cosmic_hw07b_tb;
    localparam integer TOTAL_SEQUENCES=320;
    localparam integer TICKS_PER_SEQUENCE=12;
    localparam integer TOTAL_TICKS=3840;
    localparam integer TOTAL_RECEIPTS={total_receipts};

    reg clk=0, reset=1, tick_valid=0, receipt_ready=1;
    reg [511:0] stimulus_bus=0;
    wire tick_ready;
    wire [127:0] c_phase, r_phase;
    wire [63:0] c_active, r_active, c_changed, r_changed, c_dirty, r_dirty;
    wire r_valid;
    wire [39:0] r_data;
    wire [2:0] r_occ;
    wire r_pending, r_enq, r_deq;
    wire control_tick_en = tick_valid && tick_ready;

    reg [511:0] stim_mem [0:TOTAL_TICKS-1];
    reg [127:0] state_mem [0:TOTAL_TICKS-1];
    reg [63:0] active_mem [0:TOTAL_TICKS-1];
    reg [63:0] changed_mem [0:TOTAL_TICKS-1];
    reg [63:0] dirty_mem [0:TOTAL_TICKS-1];
    reg [1:0] pattern_mem [0:TOTAL_SEQUENCES-1];
    reg [2:0] group_mem [0:TOTAL_SEQUENCES-1];
    reg [15:0] seq_receipt_mem [0:TOTAL_SEQUENCES-1];
    reg [39:0] receipt_mem [0:TOTAL_RECEIPTS-1];

    integer seq, local_tick, tick_index, physical_cycle, ready_before;
    integer receipts_seen=0, seq_receipts_seen=0, accepted_ticks=0, checks=0;
    integer enqueue_count=0, dequeue_count=0, serializer_active_cycles=0, physical_cycles_total=0;
    integer stalls_g0=0, stalls_g1=0, stalls_g2=0, stalls_g3=0, stalls_g4=0;
    integer max_g0=0, max_g1=0, max_g2=0, max_g3=0, max_g4=0;
    integer watchdog;

    always #5 clk=~clk;

    cosmic_hw06_sparse_mesh64 C(
        .clk(clk),.reset(reset),.tick_en(control_tick_en),.stimulus_bus(stimulus_bus),
        .phase_bus(c_phase),.active_mask(c_active),.changed_mask(c_changed),.dirty_mask(c_dirty));
    {top} R(
        .clk(clk),.reset(reset),.tick_valid(tick_valid),.tick_ready(tick_ready),.stimulus_bus(stimulus_bus),
        .phase_bus(r_phase),.active_mask(r_active),.changed_mask(r_changed),.dirty_mask(r_dirty),
        .receipt_valid(r_valid),.receipt_ready(receipt_ready),.receipt_data(r_data),
        .batch_occupancy(r_occ),.pending_observation(r_pending),
        .batch_enqueue_pulse(r_enq),.batch_dequeue_pulse(r_deq));

    function ready_for_cycle;
        input [1:0] pattern;
        input integer cycle;
        begin
            case(pattern)
                2'd0: ready_for_cycle=1'b1;
                2'd1: ready_for_cycle=((cycle % 4) != 3);
                2'd2: ready_for_cycle=((cycle % 2) == 0);
                2'd3: ready_for_cycle=((cycle % 16) >= 8);
                default: ready_for_cycle=1'b0;
            endcase
        end
    endfunction

    task note_stall; input [2:0] group; begin
        case(group)
            3'd0: stalls_g0=stalls_g0+1;
            3'd1: stalls_g1=stalls_g1+1;
            3'd2: stalls_g2=stalls_g2+1;
            3'd3: stalls_g3=stalls_g3+1;
            default: stalls_g4=stalls_g4+1;
        endcase
    end endtask

    task note_occ; input [2:0] group; input [2:0] occ; begin
        case(group)
            3'd0: if(occ>max_g0) max_g0=occ;
            3'd1: if(occ>max_g1) max_g1=occ;
            3'd2: if(occ>max_g2) max_g2=occ;
            3'd3: if(occ>max_g3) max_g3=occ;
            default: if(occ>max_g4) max_g4=occ;
        endcase
    end endtask

    always @(posedge clk) begin
        if(!reset) begin
            if(r_valid) serializer_active_cycles=serializer_active_cycles+1;
            if(r_valid && receipt_ready) begin
                if(receipts_seen>=TOTAL_RECEIPTS) $fatal(1,"phantom receipt beyond oracle");
                if(r_data!==receipt_mem[receipts_seen])
                    $fatal(1,"{tag} receipt mismatch index=%0d got=%h exp=%h",receipts_seen,r_data,receipt_mem[receipts_seen]);
                receipts_seen=receipts_seen+1;
                seq_receipts_seen=seq_receipts_seen+1;
                checks=checks+1;
            end
        end
    end

    always @(negedge clk) begin
        if(!reset) begin
            if(r_enq) enqueue_count=enqueue_count+1;
            if(r_deq) dequeue_count=dequeue_count+1;
            note_occ(group_mem[seq],r_occ);
        end
    end

    task reset_models; begin
        tick_valid=0; stimulus_bus=0; receipt_ready=1; reset=1;
        repeat(2) @(posedge clk); #1; reset=0;
        seq_receipts_seen=0; physical_cycle=0;
    end endtask

    task drive_one_tick; input integer index; input [1:0] pattern; input [2:0] group;
        integer accepted;
        begin
            accepted=0;
            while(!accepted) begin
                stimulus_bus=stim_mem[index]; tick_valid=1;
                receipt_ready=ready_for_cycle(pattern,physical_cycle); #1;
                ready_before=tick_ready;
                if(!ready_before) note_stall(group);
                @(posedge clk); #1;
                physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1;
                if(ready_before) begin
                    accepted=1; accepted_ticks=accepted_ticks+1;
                    if(c_phase!==state_mem[index] || r_phase!==state_mem[index]) $fatal(1,"{tag} state mismatch tick=%0d",index);
                    if(c_phase!==r_phase) $fatal(1,"{tag} execution contamination tick=%0d",index);
                    if(c_active!==active_mem[index] || r_active!==active_mem[index]) $fatal(1,"{tag} active mismatch tick=%0d",index);
                    if(c_changed!==changed_mem[index] || r_changed!==changed_mem[index]) $fatal(1,"{tag} changed mismatch tick=%0d",index);
                    if(c_dirty!==dirty_mem[index] || r_dirty!==dirty_mem[index]) $fatal(1,"{tag} dirty mismatch tick=%0d",index);
                    checks=checks+7;
                end
            end
        end
    endtask

    task drain_sequence; input [1:0] pattern; input [2:0] group; input integer expected_receipts;
        begin
            tick_valid=0; stimulus_bus=0; watchdog=0;
            while((seq_receipts_seen<expected_receipts) || r_pending || (r_occ!=0)) begin
                receipt_ready=ready_for_cycle(pattern,physical_cycle);
                @(posedge clk); #1;
                physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1;
                watchdog=watchdog+1;
                if(watchdog>10000) $fatal(1,"{tag} drain watchdog seq=%0d",seq);
            end
            if(seq_receipts_seen!=expected_receipts)
                $fatal(1,"{tag} missing/duplicate receipts seq=%0d got=%0d exp=%0d",seq,seq_receipts_seen,expected_receipts);
            receipt_ready=ready_for_cycle(pattern,physical_cycle);
            @(posedge clk); #1;
            physical_cycle=physical_cycle+1; physical_cycles_total=physical_cycles_total+1;
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

        for(seq=0;seq<TOTAL_SEQUENCES;seq=seq+1) begin
            reset_models();
            for(local_tick=0;local_tick<TICKS_PER_SEQUENCE;local_tick=local_tick+1) begin
                tick_index=seq*TICKS_PER_SEQUENCE+local_tick;
                drive_one_tick(tick_index,pattern_mem[seq],group_mem[seq]);
            end
            drain_sequence(pattern_mem[seq],group_mem[seq],seq_receipt_mem[seq]);
        end

        tick_valid=0; receipt_ready=1;
        if(receipts_seen!=TOTAL_RECEIPTS) $fatal(1,"{tag} global receipt mismatch got=%0d exp=%0d",receipts_seen,TOTAL_RECEIPTS);
        if(enqueue_count!=dequeue_count) $fatal(1,"{tag} batch write/read mismatch");
        $display("COSMIC_HW07B_{tag} PASS checks=%0d ticks=%0d receipts=%0d enq=%0d deq=%0d serializer=%0d physical=%0d stalls_g0=%0d stalls_g1=%0d stalls_g2=%0d stalls_g3=%0d stalls_g4=%0d max_g0=%0d max_g1=%0d max_g2=%0d max_g3=%0d max_g4=%0d",
            checks,accepted_ticks,receipts_seen,enqueue_count,dequeue_count,serializer_active_cycles,physical_cycles_total,
            stalls_g0,stalls_g1,stalls_g2,stalls_g3,stalls_g4,max_g0,max_g1,max_g2,max_g3,max_g4);
        $finish;
    end
endmodule
"""


def parse_sim(text: str, tag: str) -> dict:
    m = re.search(
        rf"COSMIC_HW07B_{tag} PASS checks=(\d+) ticks=(\d+) receipts=(\d+) enq=(\d+) deq=(\d+) "
        r"serializer=(\d+) physical=(\d+) stalls_g0=(\d+) stalls_g1=(\d+) stalls_g2=(\d+) stalls_g3=(\d+) stalls_g4=(\d+) "
        r"max_g0=(\d+) max_g1=(\d+) max_g2=(\d+) max_g3=(\d+) max_g4=(\d+)",
        text,
    )
    if not m:
        raise ValueError(f"{tag} PASS marker not found")
    v=list(map(int,m.groups()))
    return {
        "checks": v[0], "accepted_ticks": v[1], "receipts_emitted": v[2],
        "batch_fifo_writes": v[3], "batch_fifo_reads": v[4],
        "serializer_active_cycles": v[5], "physical_cycles": v[6],
        "backpressure_stalls": dict(zip(STALL_KEYS,v[7:12])),
        "max_reserved_occupancy": dict(zip(STALL_KEYS,v[12:17])),
    }


def cell_counts_from_json(path: Path, top: str) -> dict:
    data=json.loads(path.read_text())
    module=data["modules"][top]
    counts=Counter(cell.get("type","") for cell in module.get("cells",{}).values())
    lut=sum(n for t,n in counts.items() if re.fullmatch(r"LUT[1-6]",t))
    ff=sum(n for t,n in counts.items() if t in {"FDRE","FDSE","FDCE","FDPE"})
    bram=sum(n for t,n in counts.items() if t.startswith("RAMB18") or t.startswith("RAMB36"))
    lutram=sum(n for t,n in counts.items() if t.startswith("RAM32") or t.startswith("RAM64") or t.startswith("RAM128"))
    io=sum(n for t,n in counts.items() if t in {"IBUF","OBUF","OBUFT","IOBUF"})
    total=sum(counts.values())
    return {"total_mapped_cells":total,"core_cells_excluding_io":total-io,"lut":lut,"ff":ff,"bram":bram,"lutram":lutram}


def synthesize(yosys: str, files: list[Path], top: str, tmp: Path) -> dict:
    joined=" ".join(str(p) for p in files)
    json_path=tmp/f"{top}.json"
    run_cmd([yosys,"-q","-p",f"read_verilog -sv {joined}; hierarchy -check -top {top}; flatten; synth_xilinx -family xc7 -top {top}; write_json {json_path}"])
    row=cell_counts_from_json(json_path,top)
    depth=run_cmd([yosys,"-p",f"read_verilog -sv {joined}; hierarchy -check -top {top}; proc; memory_map; opt; flatten; opt; ltp -noff"])
    row["logic_depth_proxy"]=parse_ltp(depth)
    return row


def vector_for_pareto(sim: dict, synth: dict) -> dict:
    return {
        "lut": synth["lut"],
        "ff": synth["ff"],
        "core_cells_excluding_io": synth["core_cells_excluding_io"],
        "logic_depth_proxy": synth["logic_depth_proxy"],
        **{f"stall_{k}": sim["backpressure_stalls"][k] for k in STALL_KEYS},
    }


def dominates(a: dict, b: dict) -> bool:
    return all(a[k] <= b[k] for k in PARETO_KEYS) and any(a[k] < b[k] for k in PARETO_KEYS)


def run() -> dict:
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/"benchmarks"/"cosmic_hw_07b_manifest.json").read_text())
    assert manifest["experiment_id"]==PROTOCOL
    assert manifest["parent_hw07_head"]=="1e71648e1a2f375d7eeb3147a301a81dc8bc2399"
    stress=validate_stress_corpus()
    assert stress["fingerprint"]==manifest["stress_fingerprint"]
    oracle=build_oracle()

    iverilog=require_tool("iverilog"); vvp=require_tool("vvp"); yosys=require_tool("yosys")
    rtl06=root/"rtl"/"cosmic_hw_06.v"
    rtl07=root/"rtl"/"cosmic_hw_07_receipt.v"
    rtl07b=root/"rtl"/"cosmic_hw_07b_receipt.v"
    files=[rtl06,rtl07,rtl07b]

    simulation={}; synthesis={}
    with tempfile.TemporaryDirectory(prefix="cosmic-hw-07b-") as td:
        tmp=Path(td); mem=prepare_memories(oracle,tmp)
        for name,spec in SYSTEMS.items():
            tag=name.replace("CANDIDATE_","").replace("CONTROL_","")
            tb=tmp/f"{tag}.v"; tb.write_text(make_testbench(spec["top"],oracle,mem,tag),encoding="utf-8")
            simbin=tmp/f"{tag}.out"
            run_cmd([iverilog,"-g2012","-s","cosmic_hw07b_tb","-o",str(simbin),*(str(p) for p in files),str(tb)])
            simulation[name]=parse_sim(run_cmd([vvp,str(simbin)]),tag)
            synthesis[name]=synthesize(yosys,files,spec["top"],tmp)
            synthesis[name]["declared_receipt_state_bits"]=848*spec["depth"]+688
            synthesis[name]["fifo_depth"]=spec["depth"]
            synthesis[name]["selector"]=spec["selector"]

    official=manifest["frozen_control"]["official_hw07"]
    control=simulation["CONTROL_F4_FLAT"]
    control_gate=(
        control["receipts_emitted"]==official["receipts"]
        and control["accepted_ticks"]==official["accepted_ticks"]
        and control["batch_fifo_writes"]==official["batch_fifo_writes"]
        and control["batch_fifo_reads"]==official["batch_fifo_reads"]
        and control["physical_cycles"]==official["physical_cycles"]
        and control["serializer_active_cycles"]==official["serializer_active_cycles"]
        and control["backpressure_stalls"]==official["backpressure_stalls"]
    )

    expected_receipts=len(oracle["receipts"])
    semantic_gates={name:(
        sim["accepted_ticks"]==3840
        and sim["receipts_emitted"]==expected_receipts
        and sim["batch_fifo_writes"]==sim["batch_fifo_reads"]
    ) for name,sim in simulation.items()}

    f4_stall_gate=(simulation["CANDIDATE_F4_HIER"]["backpressure_stalls"]==control["backpressure_stalls"])

    vectors={name:vector_for_pareto(simulation[name],synthesis[name]) for name in SYSTEMS}
    frontier=[]; dominated_by={}
    for name in SYSTEMS:
        dominators=[other for other in SYSTEMS if other!=name and dominates(vectors[other],vectors[name])]
        if dominators: dominated_by[name]=dominators
        else: frontier.append(name)

    eligible=[]
    for name in SYSTEMS:
        sim=simulation[name]; syn=synthesis[name]
        if (
            semantic_gates[name]
            and sim["backpressure_stalls"]["0.01"]==0
            and sim["backpressure_stalls"]["0.05"]<=542
            and syn["logic_depth_proxy"]<=266
        ):
            eligible.append(name)

    def handoff_key(name: str):
        syn=synthesis[name]
        return (syn["core_cells_excluding_io"],syn["ff"],syn["lut"],syn["logic_depth_proxy"])

    hw08_selected=min(eligible,key=handoff_key) if eligible else "CONTROL_F4_FLAT"
    candidate_improvement=(hw08_selected!="CONTROL_F4_FLAT" and handoff_key(hw08_selected)<=handoff_key("CONTROL_F4_FLAT"))

    if not control_gate:
        decision="CONTROL_FAILURE"
    elif not all(semantic_gates.values()) or not f4_stall_gate:
        decision="RECEIPT_SEMANTIC_FAILURE"
    elif not candidate_improvement:
        decision="NO_VALID_MICROARCHITECTURE_IMPROVEMENT"
    else:
        decision="RECEIPT_FRONTIER_MEASURED"

    return {
        "benchmark_id":BENCHMARK_ID,
        "protocol":PROTOCOL,
        "decision":decision,
        "parent_hw07_head":manifest["parent_hw07_head"],
        "stress_fingerprint":stress["fingerprint"],
        "control_reproduction_gate":control_gate,
        "semantic_gates":semantic_gates,
        "f4_hier_identical_stall_gate":f4_stall_gate,
        "simulation":simulation,
        "synthesis":synthesis,
        "pareto_vectors":vectors,
        "pareto_frontier":frontier,
        "dominated_by":dominated_by,
        "hw08_eligible":eligible,
        "hw08_selected":hw08_selected,
        "synthetic_combined_score_used":False,
        "timing_decisive":False,
        "sha_merkle_present":False,
        "claim_boundary":"Icarus functional simulation plus Yosys Xilinx-7 structural mapping of generic receipt microarchitectures only; no board power, placed/routed Fmax, ASIC PPA or SHA/Merkle claim."
    }


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--json",action="store_true"); args=parser.parse_args()
    print(json.dumps(run(),indent=2 if args.json else None,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
